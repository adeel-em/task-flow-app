import json
import os
import boto3

# Initialize DynamoDB and S3 clients
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

# Get environment variables
TABLE_NAME = os.environ.get("TABLE_NAME")
BUCKET_NAME = os.environ.get("BUCKET_NAME")

# Reference to DynamoDB table
table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    try:
        # Get the task_id from the path parameters
        task_id = event["pathParameters"]["task_id"]
        print(f"Deleting task with ID: {task_id}")

        # Retrieve the task from DynamoDB to get the attachment_key
        task = table.get_item(Key={"task_id": task_id}).get("Item")

        if not task:
            return {
                "statusCode": 404,
                "body": json.dumps({"message": f"Task with ID {task_id} not found."}),
            }

        # Get the attachment key to delete the file from S3
        attachment_key = task.get("attachment_key")
        if attachment_key:
            # Delete the file from S3
            s3.delete_object(Bucket=BUCKET_NAME, Key=attachment_key)
            print(f"Deleted file from S3: {attachment_key}")
        else:
            print("No attachment found for the task.")

        # Delete the task from DynamoDB
        response = table.delete_item(
            Key={"task_id": task_id},
            ConditionExpression="attribute_exists(task_id)",  # Ensure the task exists before deleting
        )

        # Verify if the delete was successful
        if response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200:
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": f"Task with ID {task_id} and its attachment deleted successfully."
                    }
                ),
            }
        else:
            raise Exception("Failed to delete task from DynamoDB.")

    except Exception as e:
        print(f"Error deleting task: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "message": "An error occurred while deleting the task.",
                    "error": str(e),
                }
            ),
        }
