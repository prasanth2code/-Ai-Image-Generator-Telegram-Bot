import json
import base64
import boto3
import http.client
import io
import os
def lambda_handler(event, context):
    data = json.loads(event['body'])
    # for testing
    # data= event['body']  
    chat_id = data['message']['chat']['id']
    text = data['message']['text']
    
    # print(chat_id)
    # print(text)
    # print(data['message']['chat']['first_name'])
    if text == '/start':
        prompt_message = "Welcome! Please type a prompt to generate an image."
        return start_message(chat_id, prompt_message)
    else:
        return process_image_generation(chat_id, text)
        
def start_message(chat_id,prompt_message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    conn= get_connection()
    headers = {"Content-type": "application/json"}
    payload = {
        "chat_id": chat_id,
        "text": prompt_message,
    }
    conn.request("POST", f"/bot{token}/sendMessage", body=json.dumps(payload), headers=headers)
    response = conn.getresponse()
    print(response.status, response.reason)
    print(response.read().decode('utf-8'))
    return response.reason
        
def process_image_generation(chat_id,text):
    bedrock_runtime = boto3.client(service_name="bedrock-runtime")
    
    body = json.dumps({
        "text_prompts": [
            {
                "text":text,
                "weight": 1
            }
        ],
        "cfg_scale": 10,
        "seed": 0,
        "steps": 50,
        "height": 768,
        "width": 1280,
    })
    
    try:
        response = bedrock_runtime.invoke_model(
            body=body,
            modelId="stability.stable-diffusion-xl-v1",
            accept="application/json",
            contentType="application/json"
        )
        response_body = json.loads(response["body"].read().decode('utf-8'))
        for key in response_body.keys():
            print(key)
        response_body = response_body['artifacts'][0]['base64']
        save_image_to_s3(response_body, text, chat_id)
        return send_image_to_telegram(chat_id, response_body, text)
    except Exception as e:
        error_message = f"An error occurred: {str(e)}.Please retry with another prompt."
        print(error_message)
        return send_image_to_telegram(chat_id, None, "'invalid_prompts', 'One or more prompts contains filtered words. Please retry with another prompt.")


def save_image_to_s3(response, text, chat_id):
    decoded_image = base64.b64decode(response)
    s3 = boto3.client('s3')
    bucket_name = os.environ.get('BUCKET_NAME')
    key = f'{chat_id}---{text}.png'
    
    try:
        s3.put_object(Body=decoded_image, Bucket=bucket_name, Key=key)
        print(f"Image saved successfully to S3 bucket: {bucket_name}/{key}")
    except Exception as e:
        print(f"Error uploading image to S3: {e}")


def get_connection():
    token = token = os.environ.get('TELEGRAM_BOT_TOKEN')  # Replace with your Telegram Bot token
    host = 'api.telegram.org'
    conn = http.client.HTTPSConnection(host)
    return conn
    
def send_image_to_telegram(chat_id, response, text):
    conn= get_connection()
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if response is None:
        headers = {"Content-type": "application/json"}
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
    
        conn.request("POST", f"/bot{token}/sendMessage", body=json.dumps(payload), headers=headers)
    else:
        caption = text
        image_bytes = base64.b64decode(response)
        
    
        boundary = '----boundary'
        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
        }
        
        body = io.BytesIO()
        body.write(f'--{boundary}\r\n'.encode('utf-8'))
        body.write(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode('utf-8'))
        if image_bytes:
            body.write(f'--{boundary}\r\n'.encode('utf-8'))
            body.write(f'Content-Disposition: form-data; name="photo"; filename="image.png"\r\n'.encode('utf-8'))
            body.write('Content-Type: image/png\r\n\r\n'.encode('utf-8'))
            body.write(image_bytes)
            body.write(f'\r\n--{boundary}\r\n'.encode('utf-8'))
        body.write(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode('utf-8'))
        body.write(f'--{boundary}--\r\n'.encode('utf-8'))
        body.seek(0)
        
        conn.request('POST', f'/bot{token}/sendPhoto', body, headers)
    response = conn.getresponse()
    print(response.status, response.reason)
    print(response.read().decode('utf-8'))
    return response.reason
