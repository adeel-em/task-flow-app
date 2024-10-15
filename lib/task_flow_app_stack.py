import os
from dotenv import load_dotenv
from aws_cdk import (
    Duration,
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_cognito as cognito,
    aws_s3 as s3,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    RemovalPolicy,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
)
from constructs import Construct
from aws_cdk.aws_lambda_python_alpha import PythonFunction


class TaskFlowAppStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        load_dotenv()
        SES_EMAIL_SENDER = os.getenv("SES_EMAIL_SENDER")
        CALLBACK_URL = os.getenv("CALLBACK_URL")
        LOGOUT_URL = os.getenv("LOGOUT_URL")

        # Creating SNS Topic
        alarm_topic = sns.Topic(
            self, "TaskFlowAlarmTopic", display_name="Task Flow API Alarm Notifications"
        )

        # Creating a CloudWatch alarm action to send notifications to SNS topic
        alarm_topic.add_subscription(subs.EmailSubscription(SES_EMAIL_SENDER))

        # Creating S3 bucket
        bucket = s3.Bucket(
            self,
            "TaskFilesBucket",
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ACLS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Creating a DynamoDB table
        table = dynamodb.Table(
            self,
            "TasksTable",
            partition_key=dynamodb.Attribute(
                name="task_id", type=dynamodb.AttributeType.STRING
            ),
            table_name="tasks",
        )

        # Adding a GSI for querying by user_id and status
        table.add_global_secondary_index(
            index_name="user-status-index",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Creating a Cognito User Pool
        user_pool = cognito.UserPool(
            self,
            "TaskFlowUserPool",
            user_pool_name="TaskFlowUserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes={"email": {"required": True}},
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
        )

        user_pool.add_domain(
            "CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix="taskflow-app"),
        )

        # Creating a Cognito User Pool Client
        user_pool_client = cognito.UserPoolClient(
            self,
            "TaskFlowUserPoolClient",
            user_pool=user_pool,
            generate_secret=True,
            auth_flows=cognito.AuthFlow(
                admin_user_password=True,
                custom=True,
                user_password=True,
                user_srp=True,
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True,
                ),
                scopes=[cognito.OAuthScope.OPENID],
                callback_urls=[CALLBACK_URL],
                logout_urls=[LOGOUT_URL],
            ),
        )

        # Creating API Gateway
        api = apigateway.RestApi(
            self,
            "TaskFlowApi",
            rest_api_name="TaskFlow Service",
            description="API for Task Management app",
        )

        # Lambda Functions
        get_tasks_lambda = PythonFunction(
            self,
            "GetTasksFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            entry="lambda/get_tasks",
            index="get_tasks.py",
            handler="lambda_handler",
            memory_size=128,
            timeout=Duration.seconds(10),
            environment={
                "TABLE_NAME": table.table_name,
                "BUCKET_NAME": bucket.bucket_name,
            },
        )

        create_task_lambda = PythonFunction(
            self,
            "CreateTaskFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            entry="lambda/create_task",
            index="create_task.py",
            handler="lambda_handler",
            memory_size=128,
            timeout=Duration.seconds(10),
            environment={
                "TABLE_NAME": table.table_name,
                "BUCKET_NAME": bucket.bucket_name,
                "SES_EMAIL_SENDER": SES_EMAIL_SENDER,
            },
        )

        update_task_lambda = PythonFunction(
            self,
            "UpdateTaskFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            entry="lambda/update_task",
            index="update_task.py",
            handler="lambda_handler",
            memory_size=128,
            timeout=Duration.seconds(10),
            environment={
                "TABLE_NAME": table.table_name,
                "BUCKET_NAME": bucket.bucket_name,
                "SES_EMAIL_SENDER": SES_EMAIL_SENDER,
            },
        )

        delete_task_lambda = PythonFunction(
            self,
            "DeleteTaskFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            entry="lambda/delete_task",
            index="delete_task.py",
            handler="lambda_handler",
            memory_size=128,
            timeout=Duration.seconds(10),
            environment={
                "TABLE_NAME": table.table_name,
                "BUCKET_NAME": bucket.bucket_name,
            },
        )

        # Adding Cognito Authorizer to API Gateway
        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self, "TaskFlowApiAuthorizer", cognito_user_pools=[user_pool]
        )

        # Creating a CloudWatch metric for API Gateway hits
        post_method_metric = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="Count",
            dimensions_map={
                "ApiName": api.rest_api_name,
            },
            period=Duration.minutes(1),
            statistic="Sum",
        )

        # Creating a CloudWatch alarm when API Gateway is hit more than 5 times in 1 minute
        post_api_alarm = cloudwatch.Alarm(
            self,
            "PostApiHitsAlarm",
            metric=post_method_metric,
            threshold=5,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alarm when POST /task API is hit more than 5 times in one minute",
            actions_enabled=True,
        )
        post_api_alarm.add_alarm_action(cloudwatch_actions.SnsAction(alarm_topic))

        # Creating a CloudWatch metric for POST request payload size
        payload_size_metric = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="RequestPayloadSize",
            dimensions_map={
                "ApiName": api.rest_api_name,
                "Resource": "/task",
                "Method": "POST",
                "Stage": "prod",
            },
            period=Duration.minutes(1),
            statistic="Max",
        )

        # Creating a CloudWatch alarm when POST request payload size exceeds 5 MB (5242880 bytes)
        payload_size_alarm = cloudwatch.Alarm(
            self,
            "PostApiPayloadSizeAlarm",
            metric=payload_size_metric,
            threshold=5242880,  # 5 MB in bytes
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alarm when POST /task API payload size exceeds 5 MB",
            actions_enabled=True,
        )
        payload_size_alarm.add_alarm_action(cloudwatch_actions.SnsAction(alarm_topic))

        # Integrating Lambda with API Gateway
        task_resource = api.root.add_resource("task")
        task_id_resource = task_resource.add_resource("{task_id}")
        task_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(get_tasks_lambda),
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )
        task_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(create_task_lambda),
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )
        task_id_resource.add_method(
            "PUT",
            apigateway.LambdaIntegration(update_task_lambda),
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )
        task_id_resource.add_method(
            "DELETE", apigateway.LambdaIntegration(delete_task_lambda)
        )

        # Granting permissions
        bucket.grant_put(create_task_lambda)
        bucket.grant_put(update_task_lambda)
        table.grant_read_data(get_tasks_lambda)
        table.grant_write_data(create_task_lambda)
        table.grant_read_write_data(update_task_lambda)
        table.grant_full_access(delete_task_lambda)
        bucket.grant_delete(delete_task_lambda)
        create_task_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )
        update_task_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )
