import asyncio
import aiohttp
import os
import json
from typing import Optional
from pydantic import BaseModel, Field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Master(BaseModel):
    id: int
    name: Optional[str] = None
    
    class Config:
        extra = "allow"


class ServiceDetails(BaseModel):
    title: str = Field(default="")
    name: str = Field(default="")
    staff: list = Field(default_factory=list)
    price_min: Optional[float] = Field(default=None)
    price_max: Optional[float] = Field(default=None)
    
    class Config:
        extra = "allow"
    
    def get_title(self) -> str:
        return self.title or self.name


class YclientsService:
    def __init__(self):
        self.auth_header = os.getenv('AUTH_HEADER') or os.getenv('AuthenticationToken')
        self.company_id = os.getenv('COMPANY_ID') or os.getenv('CompanyID')
        
        if not self.auth_header:
            raise ValueError("Не задан AUTH_HEADER или AuthenticationToken")
        if not self.company_id:
            raise ValueError("Не задан COMPANY_ID или CompanyID")
    
    async def get_service_details(self, service_id: int) -> ServiceDetails:
        url = f"https://api.yclients.com/api/v1/company/{self.company_id}/services/{service_id}"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                response_data = await response.json()
                service_data = response_data.get('data', response_data)
                return ServiceDetails(**service_data)


SERVICE_IDS = [
    16659735, 16659736, 16659734, 16659733, 16659737, 16659748, 16659743,
    16845288, 16845287, 16845285, 16845286, 16845289, 16845290, 16845279,
    16659738, 16659739, 16659740, 16659741, 16845277, 16845278, 16845296, 16845297,
    16699566, 16699567, 16699568, 16699569, 16699570,
    16659801, 16659802, 16659804, 16659805, 16659821, 18423373,
    16699798, 16699799, 16699801, 16699808, 16699812, 16699813, 16699815, 16699822,
    16659808, 16659809, 16659820, 16985006, 17379339, 17379392,
    17379602, 17786219, 17786272, 17823049, 17823487, 17831658, 17831668, 21144588,
    16699836, 16699839, 16699853, 16699859, 16699865, 16699867, 16699869, 23433927,
    16699711, 16699715, 16699718, 16699722, 16699724, 16699737, 16699738, 18709540,
    16699646, 16699648, 16699649, 18709510, 18709522, 18839714, 18877685, 19120572,
    16699629, 16699632, 16699633, 16699636, 16699637, 16699638, 16699639,
    16699751, 16699753, 16699755, 16699758, 18709550, 18709559, 18709562, 18912641,
    18912600, 18912607, 18912612, 18912625, 18912629, 18912719, 18912731, 18912742, 18912762, 18912767
]


def format_price(price_min: Optional[float], price_max: Optional[float]) -> str:
    if price_min is None and price_max is None:
        return ""
    if price_min is None or price_min == 0:
        if price_max and price_max > 0:
            return str(int(price_max))
        return ""
    if price_max is None or price_max == 0:
        return str(int(price_min))
    if price_min == price_max:
        return str(int(price_min))
    if price_max > price_min:
        return f"{int(price_min)}-{int(price_max)}"
    return str(int(price_min))


async def get_price(yclients_service, service_id):
    try:
        service_details = await yclients_service.get_service_details(service_id)
        return {
            "service_id": service_id,
            "success": True,
            "price": format_price(service_details.price_min, service_details.price_max)
        }
    except Exception as e:
        return {
            "service_id": service_id,
            "success": False,
            "price": None,
            "error": str(e)
        }


async def main():
    print("Загружаю цены...\n")
    
    yclients_service = YclientsService()
    tasks = [get_price(yclients_service, service_id) for service_id in SERVICE_IDS]
    results = await asyncio.gather(*tasks)
    
    # Создаем словарь ID -> цена
    price_map = {}
    for result in results:
        if result.get("success"):
            price_map[result["service_id"]] = result["price"]
        else:
            print(f"Ошибка для ID {result['service_id']}: {result.get('error', 'неизвестно')}")
    
    # Читаем файл
    services_file = Path(__file__).parent / "Files" / "services.json"
    with open(services_file, 'r', encoding='utf-8') as f:
        services_data = json.load(f)
    
    # Обновляем цены
    updated_count = 0
    for category_key, category_data in services_data.items():
        if not isinstance(category_data, dict):
            continue
        services = category_data.get('services', [])
        if not isinstance(services, list):
            continue
        
        for service in services:
            if not isinstance(service, dict):
                continue
            service_id = service.get('id')
            if service_id and service_id in price_map:
                old_price = service.get('prices', '')
                new_price = price_map[service_id]
                if old_price != new_price:
                    service['prices'] = new_price
                    updated_count += 1
                    print(f"ID {service_id}: {old_price} -> {new_price}")
    
    # Сохраняем файл
    with open(services_file, 'w', encoding='utf-8') as f:
        json.dump(services_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nОбновлено услуг: {updated_count}")
    print("Файл сохранен!")


if __name__ == "__main__":
    asyncio.run(main())

