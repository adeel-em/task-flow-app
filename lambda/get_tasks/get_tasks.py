import json
import os
import boto3
from boto3.dynamodb.conditions import Key, And  # Import Key and And conditions

BUCKET_NAME = os.environ.get("BUCKET_NAME")
TABLE_NAME = os.environ.get("TABLE_NAME")


def lambda_handler(event, context):

    print("event", event)
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TABLE_NAME)

    try:
        claims = event["requestContext"]["authorizer"]["claims"]
        user_id = claims["sub"]  # This is the unique user ID
        print(f"User ID (sub): {user_id}")

        # You can also extract other claims if needed
        email = claims.get("email", "No email found")
        print(f"User email: {email}")

        query_params = event.get("queryStringParameters", {})
        status = None
        if query_params is not None:
            status = query_params.get("status", None)

        print(f"Status: {status}")

        if status:
            # Combine the conditions using And()
            response = table.query(
                IndexName="user-status-index",
                KeyConditionExpression=And(
                    Key("status").eq(status), Key("user_id").eq(user_id)
                ),
            )
        else:
            response = table.query(
                IndexName="user-status-index",
                KeyConditionExpression=Key("user_id").eq(user_id),
            )

        # Check if response is None
        if response is None:
            print("No response from DynamoDB. Check the query conditions and index.")
            return {
                "statusCode": 500,
                "body": json.dumps({"message": "No response from DynamoDB"}),
            }

        # Debugging: Print the response for visibility
        print("DynamoDB response:", response)

        tasks = response.get("Items", [])
        return {"statusCode": 200, "body": json.dumps(tasks)}

    except Exception as e:
        print("error", e)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": "Failed to get tasks from DynamoDB", "error": str(e)}
            ),
        }
