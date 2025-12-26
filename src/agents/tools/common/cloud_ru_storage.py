"""
Общий модуль для работы с Cloud.ru Object Storage
"""
import os
import json
import boto3
from typing import Dict


def get_cloud_ru_s3_client():
    """
    Создает и возвращает клиент boto3 для работы с Cloud.ru S3
    
    Returns:
        boto3.client: Клиент S3 для Cloud.ru
        
    Raises:
        ValueError: если не заданы необходимые переменные окружения
        ImportError: если не установлен boto3
    """
    # Получаем Tenant ID
    tenant_id = os.getenv('CLOUD_RU_TENANT_ID') or os.getenv('TENANT_ID')
    
    # Получаем Key ID и Key Secret
    key_id = (
        os.getenv('CLOUD_RU_S3_KEY_ID') or 
        os.getenv('S3_KEY_ID') or 
        os.getenv('KEY_ID')
    )
    key_secret = (
        os.getenv('CLOUD_RU_S3_KEY_SECRET') or 
        os.getenv('S3_KEY_SECRET') or 
        os.getenv('KEY_SECRET')
    )
    
    # Проверяем наличие всех необходимых переменных
    if not tenant_id:
        raise ValueError("Не задан CLOUD_RU_TENANT_ID или TENANT_ID")
    if not key_id:
        raise ValueError("Не задан CLOUD_RU_S3_KEY_ID/S3_KEY_ID/KEY_ID")
    if not key_secret:
        raise ValueError("Не задан CLOUD_RU_S3_KEY_SECRET/S3_KEY_SECRET/KEY_SECRET")
    
    # Проверяем, что ключи не пустые
    tenant_id = tenant_id.strip()
    key_id = key_id.strip()
    key_secret = key_secret.strip()
    
    if not tenant_id or not key_id or not key_secret:
        raise ValueError("Tenant ID, Key ID и Key Secret не могут быть пустыми")
    
    # Формируем Access Key ID в формате Cloud.ru: <tenant_id>:<key_id>
    access_key_id = f"{tenant_id}:{key_id}"
    
    # Создаем клиент согласно документации Cloud.ru
    s3 = boto3.client(
        's3',
        endpoint_url='https://s3.cloud.ru',
        region_name='ru-central-1',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=key_secret
    )
    
    return s3


def load_json_from_cloud_ru(bucket_name: str, file_path: str) -> Dict:
    """
    Загружает JSON файл из Cloud.ru Object Storage
    
    Args:
        bucket_name: Имя бакета
        file_path: Путь к файлу в бакете
        
    Returns:
        Dict: Содержимое JSON файла
        
    Raises:
        ValueError: если не заданы необходимые переменные окружения
        ImportError: если не установлен boto3
        Exception: если произошла ошибка при загрузке файла
        json.JSONDecodeError: если ошибка парсинга JSON
    """
    if not bucket_name:
        raise ValueError("Не задано имя бакета")
    
    try:
        s3 = get_cloud_ru_s3_client()
        response = s3.get_object(Bucket=bucket_name, Key=file_path)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        error_details = f"Ошибка при загрузке файла из Cloud.ru S3:\n"
        error_details += f"  Bucket: {bucket_name}\n"
        error_details += f"  Key: {file_path}\n"
        error_details += f"  Endpoint: https://s3.cloud.ru\n"
        error_details += f"  Region: ru-central-1\n"
        error_details += f"  Ошибка: {str(e)}\n"
        error_details += f"  Тип ошибки: {type(e).__name__}"
        
        # Если это ошибка аутентификации, добавляем подсказку
        if 'InvalidAccessKeyId' in str(e) or 'AccessDenied' in str(e):
            error_details += f"\n\nВНИМАНИЕ: Проблема с ключами доступа!\n"
            error_details += f"  - Убедитесь, что Tenant ID правильный (из страницы с бакетами)\n"
            error_details += f"  - Проверьте, что Key ID и Key Secret - это ключи для Cloud.ru S3\n"
            error_details += f"  - Access Key ID должен быть в формате: tenant_id:key_id\n"
            error_details += f"  - Убедитесь, что ключи имеют права на чтение бакета {bucket_name}"
        
        raise Exception(error_details) from e



