import aiomysql
import asyncio
from config.config import Config
from sendqueue import QueueDB
import re
import time
from typing import Optional

config = Config()
park_admin = config.get_config('park_admin')[0]


async def send_remind(tips: str, receiver: str, produce: str = 'parking') -> None:
    mid = str(time.time().__int__())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, '', produce)


class ParkingMonitor:
    def __init__(self):
        self._last_record_time: Optional[str] = None
        self._db_pool: Optional[aiomysql.Pool] = None
        db_config = config.get_config('park_db')
        # 调整数据库配置参数
        self._db_config = {
            'host': db_config['host'],
            'port': db_config.get('port', 3306),  # Default MySQL port if not specified
            'user': db_config['user'],
            'password': db_config['password'],
            'db': db_config['database'],
            'charset': db_config.get('charset', 'utf8mb4')
        }

    async def init_db_pool(self):
        if not self._db_pool:
            self._db_pool = await aiomysql.create_pool(**self._db_config)
    
    async def close(self):
        if self._db_pool:
            self._db_pool.close()
            await self._db_pool.wait_closed()

    async def get_parking_records(self, record) -> None:
        r = re.match(r'车辆进出查询(\d*)', record.content)
        try:
            cnts = int(r.group(1))
        except:
            cnts = 10

        try:
            await self.init_db_pool()
            async with self._db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = """
                        SELECT 
                            InOutTime,
                            Plate, 
                            UserName, 
                            IOType
                        FROM inoutrecord 
                        ORDER BY InOutTime DESC 
                        LIMIT %s
                    """
                    await cursor.execute(query, (cnts,))
                    records = await cursor.fetchall()
                    
                    tips = f"最新{cnts}条记录:"
                    for record in sorted(records, key=lambda x: x[0], reverse=True):
                        tips += f"\n时间: {record[0]}, 车牌: {record[1]}, 用户: {record[2]}, 类型: {record[3]}"
                    print(tips)
                    await send_remind(tips, park_admin)
        except Exception as e:
            await send_remind(f"查询数据库时出错: {e}", park_admin)

    async def watching_parking(self) -> None:
        try:
            await self.init_db_pool()
            async with self._db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = """
                        SELECT 
                            InOutTime,
                            Plate, 
                            UserName, 
                            IOType
                        FROM inoutrecord 
                        ORDER BY InOutTime DESC 
                        LIMIT 1
                    """
                    await cursor.execute(query)
                    record = await cursor.fetchone()
                    
                    if not record:
                        print("No record found.")
                        return
                        
                    if self._last_record_time != record[0]:
                        self._last_record_time = record[0]
                        tips = f"车辆{record[3]}:\n{record[0]} {record[2]} {record[1]}"
                        print(tips)
                        await send_remind(tips, park_admin)
                        
        except Exception as e:
            await send_remind(f"监控数据库时出错: {e}", park_admin)


# 创建全局监控实例
parking_monitor = ParkingMonitor()

# 导出供外部使用的函数
async def get_parking_records(record):
    await parking_monitor.get_parking_records(record)

async def watching_parking():
    await parking_monitor.watching_parking()
