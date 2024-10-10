from datetime import datetime
import json
import os
import uuid
import boto3
import base64
from requests_toolbelt.multipart import decoder

BUCKET_NAME = os.environ.get("BUCKET_NAME")
TABLE_NAME = os.environ.get("TABLE_NAME")
SES_EMAIL_SENDER = os.environ.get("SES_EMAIL_SENDER")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
ses = boto3.client("ses")


def lambda_handler(event, context):
    print("event", event)
    try:

        task_id = event["pathParameters"]["task_id"]
        print(f"Task ID: {task_id}")

        claims = event["requestContext"]["authorizer"]["claims"]
        user_id = claims["sub"]
        print(f"User ID (sub): {user_id}")

        body = event["body"]
        if event.get("isBase64Encoded", False):
            body = base64.b64decode(body)
        else:
            body = body.encode("utf-8")

        content_type = event["headers"].get("Content-Type", "")
        multipart_data = decoder.MultipartDecoder(body, content_type)

        title = None
        description = None
        status = None
        attachment = None

        for part in multipart_data.parts:
            content_disposition = part.headers[b"Content-Disposition"].decode()
            if 'name="title"' in content_disposition:
                title = part.text
            elif 'name="description"' in content_disposition:
                description = part.text
            elif 'name="status"' in content_disposition:
                status = part.text

        if task_id is None:
            raise Exception("Task ID not found in form data")

        # Check if there is an attachment and upload it to S3
        for part in multipart_data.parts:
            headers = part.headers.get(b"Content-Disposition", None).decode("utf-8")
            if "filename=" in headers:
                attachment = upload_attachment(multipart_data)
                print("Attachment uploaded:", attachment)

        # Update the task in DynamoDB
        updated_task = update_task_in_db(
            task_id, title, description, status, attachment
        )
        print("Task updated:", updated_task)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {"message": f"Task updated successfully with id: {task_id}"}
            ),
        }

    except Exception as e:
        print("error", e)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": "An error occurred during task update.", "error": str(e)}
            ),
        }


def update_task_in_db(
    task_id, title=None, description=None, status=None, attachment=None
):
    try:
        # Prepare the update expression
        update_expression = "SET"
        expression_attribute_values = {}

        if title:
            update_expression += " title = :t,"
            expression_attribute_values[":t"] = title

        if description:
            update_expression += " description = :d,"
            expression_attribute_values[":d"] = description

        if status:
            update_expression += " status = :s,"
            expression_attribute_values[":s"] = status

        if attachment:
            update_expression += " attachment_key = :a_key, attachment_url = :a_url,"
            expression_attribute_values[":a_key"] = attachment["key"]
            expression_attribute_values[":a_url"] = attachment["url"]

        # Remove trailing comma
        if update_expression.endswith(","):
            update_expression = update_expression[:-1]

        # Update the item in DynamoDB
        response = table.update_item(
            Key={"task_id": task_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW",
        )

        return response["Attributes"]

    except Exception as e:
        raise Exception(f"Failed to update task in DynamoDB: {e}")


def insert_into_db(attachment, user_id=None, multipart_data=None):
    try:
        task_id = uuid.uuid4().hex
        title = None
        description = None
        status = "open"

        # Find the form fields in the multipart data
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
