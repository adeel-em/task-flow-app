from datetime import datetime
import json
import os
import uuid
import boto3
import base64
from requests_toolbelt.multipart import decoder

BUCKET_NAME = os.environ.get("BUCKET_NAME")
TABLE_NAME = os.environ.get("TABLE_NAME")
TOPIC_ARN = os.environ.get("TOPIC_ARN")
SES_EMAIL_SENDER = os.environ.get("SES_EMAIL_SENDER")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
ses = boto3.client("ses")


def lambda_handler(event, context):
    print("event", event)
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
        user_id = claims["sub"]
        print(f"User ID (sub): {user_id}")

        email = claims.get("email", "No email found")
        print(f"User email: {email}")

        body = event["body"]
        if event.get("isBase64Encoded", False):
            body = base64.b64decode(body)
        else:
            body = body.encode("utf-8")

        content_type = event["headers"].get("Content-Type", "")
        multipart_data = decoder.MultipartDecoder(body, content_type)

        # Uploading the attachment to S3
        attachment = upload_attachment(multipart_data)
        print("attachment", attachment)

        # Creating a new task
        created_task = insert_into_db(attachment, user_id, multipart_data)
        print("task created", created_task)

        # Sending email notification
        send_email(created_task, email)
        print("Notification sent")

        return {
            "body": json.dumps(
                {
                    "message": f"Task created successfully with id: {created_task["task_id"]}"
                }
            ),
        }

    except Exception as e:
        print("error", e)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": "An error occurred during task creation.", "error": str(e)}
            ),
        }


def upload_attachment(multipart_data=None):
    try:
        print("Uploading attachment")
        for part in multipart_data.parts:
            headers = part.headers.get(b"Content-Disposition", None).decode("utf-8")
            if "filename=" in headers:

                filename = headers.split("filename=")[1].strip('"')
                file_content = part.content
                file_key = f"uploads/{uuid.uuid4().hex}{filename}"

                s3 = boto3.client("s3")
                s3.put_object(Bucket=BUCKET_NAME, Key=file_key, Body=file_content)
                print("File uploaded to S3")
                return {
                    "key": file_key,
                    "url": f"https://{BUCKET_NAME}.s3.amazonaws.com/{file_key}",
                }
            else:
                print("Content-Disposition header not found")

    except (KeyError, json.JSONDecodeError) as e:
        print("error", e)
        raise Exception(f"Invalid request body: {e}")


def insert_into_db(attachment, user_id=None, multipart_data=None):
    try:
        task_id = uuid.uuid4().hex
        title = None
        description = None
        status = "open"

        # Finding form fields in the multipart data
        for part in multipart_data.parts:
            content_disposition = part.headers[b"Content-Disposition"].decode()
            if 'name="title"' in content_disposition:
                title = part.text
            elif 'name="description"' in content_disposition:
                description = part.text
            elif 'name="status"' in content_disposition:
                status = part.text

        # Check if title is found, its mandatory
        if title is None:
            raise Exception("Title not found in form data")

    except (KeyError, json.JSONDecodeError) as e:
        raise Exception("Title or description not found in form data")

    # Add the task to the DynamoDB table
    try:
        table.put_item(
            Item={
                "task_id": task_id,
                "user_id": user_id,
                "title": title,
                "description": description,
                "status": status if status else "open",
                "attachment_key": attachment["key"],
                "attachment_url": attachment["url"],
                "created_at": datetime.now().isoformat(),
            }
        )
        return {
            "task_id": task_id,
            "title": title,
        }
    except Exception as e:
        raise Exception(f"Failed to insert task into DynamoDB: {e}")


def send_email(task, recipient_email):
    print(f"Sending email from {SES_EMAIL_SENDER} to {recipient_email}")
    try:
        response = ses.send_email(
            Source=SES_EMAIL_SENDER,
            Destination={
                "ToAddresses": [recipient_email],
            },
            Message={
                "Subject": {"Data": "Task Created Successfully", "Charset": "UTF-8"},
                "Body": {
                    "Text": {
                        "Data": (
                            f"Hello,\n\n"
                            f"Your task has been created successfully with the following details:\n"
                            f"Title: {task['title']}\n"
                            f"Task ID: {task['task_id']}\n\n"
                            f"Best regards,\n"
                            f"Taskflow Team"
                        ),
                        "Charset": "UTF-8",
                    }
                },
            },
        )
        print(f"Email sent! Message ID: {response['MessageId']}")
    except Exception as e:
        print(f"Failed to send email notification: {e}")
        raise Exception(f"Failed to send email notification: {e}")
