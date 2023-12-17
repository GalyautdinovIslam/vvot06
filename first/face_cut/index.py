import boto3
import io
import json
import os
import requests
import uuid
import ydb
from PIL import Image
from botocore.config import Config


def handler(event, context):
    driver = ydb.Driver(
        endpoint=f"grpcs://{os.environ['ENDPOINT']}",
        database=os.environ["DATABASE"],
        credentials=ydb.AccessTokenCredentials(context.token["access_token"])
    )

    driver.wait(fail_fast=True, timeout=5)

    pool = ydb.SessionPool(driver)

    access_token = os.environ["ACCESS_TOKEN"]
    secret_key = os.environ["SECRET_KEY"]

    photo_bucket_id = os.environ["PHOTO_BUCKET_ID"]
    faces_bucket_id = os.environ["FACES_BUCKET_ID"]

    session = boto3.Session(
        aws_access_key_id=access_token,
        aws_secret_access_key=secret_key,
        region_name="ru-central1",
    )

    endpoint = "https://storage.yandexcloud.net"

    s3 = session.client(
        "s3", endpoint_url=endpoint, config=Config(signature_version="s3v4")
    )

    gson = json.loads(event["messages"][0]["details"]["message"]["body"])

    object_id = gson["key"]
    vertices = gson["vertices"]

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": photo_bucket_id, "Key": object_id},
        ExpiresIn=100,
    )
    r = requests.get(url=url)

    image = Image.open(io.BytesIO(r.content))

    cropped_image = image.crop(
        (int(vertices[0]["x"]), int(vertices[0]["y"]), int(vertices[2]["x"]), int(vertices[2]["y"])))

    output = io.BytesIO()
    cropped_image.save(output, 'JPEG')
    output.seek(0)

    face_key = str(uuid.uuid4()) + '.jpg'
    s3.put_object(Bucket=faces_bucket_id, Key=face_key, Body=output, ContentType="image/jpeg")

    pool.retry_operation_sync(insert_data, None, face_key, object_id)

    return {
        'statusCode': 200,
    }


def insert_data(session, face_key, photo_key):
    query = f'insert into photos(face_key , photo_key) values ("{face_key}", "{photo_key}");'
    return session.transaction().execute(
        query,
        commit_tx=True,
        settings=ydb.BaseRequestSettings().with_timeout(3).with_operation_timeout(2)
    )
