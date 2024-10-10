import os
import aws_cdk as cdk
from dotenv import load_dotenv
from lib.task_flow_app_stack import TaskFlowAppStack

load_dotenv()

app = cdk.App()

TaskFlowAppStack(
    app,
    "TaskFlowAppStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION")
    ),
)

# Synthesize the app
app.synth()
