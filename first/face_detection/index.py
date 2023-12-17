import base64
import boto3
import json
import os
import requests
from botocore.client import Config
from requests_auth_aws_sigv4 import AWSSigV4


def handler(event, context):
    cnx_access_token = context.token["access_token"]
    token_type = context.token["token_type"]

    os_access_token = os.environ["ACCESS_TOKEN"]
    secret_key = os.environ["SECRET_KEY"]

    queue_url = os.environ["QUEUE_URL"]

    session = boto3.Session(
        aws_access_key_id=os_access_token,
        aws_secret_access_key=secret_key,
        region_name="ru-central1",
    )

    endpoint = "https://storage.yandexcloud.net"

    s3 = session.client(
        "s3", endpoint_url=endpoint, config=Config(signature_version="s3v4")
    )

    bucket_id = event["messages"][0]["details"]["bucket_id"]
    object_id = event["messages"][0]["details"]["object_id"]
    folder_id = event["messages"][0]["event_metadata"]["folder_id"]

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_id, "Key": object_id},
        ExpiresIn=100,
    )
    r = requests.get(url=url)

    headers = {
        "Authorization": f"{token_type} {cnx_access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "folderId": folder_id,
        "analyze_specs": [{
            "content": base64.b64encode(r.content).decode(),
            "features": [{
                "type": "FACE_DETECTION"
            }]
        }]
    }

    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"

    r = requests.post(url=url, headers=headers, data=json.dumps(data))

    url = "https://message-queue.api.cloud.yandex.net"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    auth = AWSSigV4('sqs',
                    aws_access_key_id=os_access_token,
                    aws_secret_access_key=secret_key,
                    region="ru-central1")

    ss = r.json()
    face_detection = ss["results"][0]["results"][0]["faceDetection"]

    if "faces" in face_detection:
        for face in face_detection["faces"]:
            message = {
                "key": object_id,
                "vertices": face["boundingBox"]["vertices"]
            }
            data = {
                "Action": "SendMessage",
                "MessageBody": json.dumps(message),
                "QueueUrl": queue_url,
            }
            requests.post(
                url,
                headers=headers,
                auth=auth,
                data=data
            )

    return {
        'statusCode': 200,
    }
