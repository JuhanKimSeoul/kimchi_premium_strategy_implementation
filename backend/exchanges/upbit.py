import os
import logging
from datetime import datetime, timezone
import uuid
import aiohttp
import dotenv
import jwt
import uuid
import hashlib
from urllib.parse import urlencode, unquote
from .base import Exchange

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

class UpbitExchange(Exchange):
    """
    Upbit 거래소 API와 상호작용하기 위한 클래스.

    이 클래스는 시장 데이터를 가져오고 Upbit의 거래 서비스를 이용하기 위한 메서드를 제공합니다.
    """
    name = "upbit"
    server_url = "https://api.upbit.com"
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        
    @classmethod
    def from_env(cls):
        """
        환경 변수에서 API 키와 시크릿 키를 로드하여 UpbitExchange 인스턴스를 생성합니다.

        Returns:
            UpbitExchange: UpbitExchange 인스턴스
        """
        api_key = os.getenv("UPBIT_ACCESS_KEY")
        secret_key = os.getenv("UPBIT_SECRET_KEY")
        if not api_key or not secret_key:
            raise ValueError("UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY must be set in environment variables.")
        return cls(api_key, secret_key)

    @classmethod
    async def get_tickers(cls):
        """
        Upbit에서 KRW 티커 목록을 가져옵니다.

        Returns:
            list[str]: KRW 티커 목록 (KRW- 접두사가 제거된 티커 이름 리스트)

        Raises:
            Exception: API 호출 실패 시 발생하는 예외
        """
        try:
            url = f"{cls.server_url}/v1/market/all?is_details=true"
            headers = {"accept": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as res:
                    if res.status != 200:
                        raise Exception(f"Upbit API Error: {res.status} - {await res.text()}")
                    
                    # filter로 KRW-로 시작하는 티커만 필터링
                    krw_tickers = filter(lambda x: x['market'].startswith('KRW-'), await res.json())

                    # map으로 market에서 "KRW-"를 제거
                    processed_tickers = map(
                        lambda x: x["market"].replace("KRW-", ""), krw_tickers
                    )

                    return list(processed_tickers)
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching tickers: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while fetching tickers: {e}")
            raise

    @classmethod
    async def get_ticker_orderbook(cls, tickers: list[str], count: int = 30):
        """
        Upbit에서 여러 티커의 주문서를 한 번에 가져옵니다.

        Args:
            tickers (list[str]): 티커 이름 리스트 (예: ["BTC", "ETH"])
            level (float): 호가 모아보기 단위
            count (int): 조회할 호가 개수

        Returns:
            list[dict]: 각 티커의 표준화된 주문서 정보 리스트
        """
        try:
            markets = ",".join([f"KRW-{ticker}" for ticker in tickers])
            url = f"{cls.server_url}/v1/orderbook?markets={markets}&count={count}"
            headers = {"accept": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as res:
                    if res.status != 200:
                        raise Exception(f"Upbit API Error: {res.status} - {await res.json()}")
                    response = await res.json()
                    result = []
                    for orderbook_data in response:
                        standardized_orderbook = {
                            "ticker": orderbook_data["market"].replace("KRW-", ""),
                            "timestamp": orderbook_data["timestamp"],
                            "orderbook": [
                                {
                                    "ask_price": unit["ask_price"],
                                    "bid_price": unit["bid_price"],
                                    "ask_size": unit["ask_size"],
                                    "bid_size": unit["bid_size"]
                                }
                                for unit in orderbook_data["orderbook_units"]
                            ]
                        }
                        result.append(standardized_orderbook)
                    return result
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching orderbook for {tickers}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while fetching orderbook for {tickers}: {e}")
            raise

    @classmethod
    async def get_ticker_ob_price(cls, ticker: str):
        """
        Upbit에서 현재 티커 가격을 가져옵니다.
        실제 가격을 가져오는 것이 아닌 매수기준 최저호가창의 가격을 가져옵니다.

        Returns:
            dict: 티커 가격 정보 (예: {"ticker": "BTC", "price": 50000})

        Raises:
            Exception: API 호출 실패 시 발생하는 예외
        """
        try:
            orderbook = await cls.get_ticker_orderbook([ticker])
            if orderbook and orderbook[0]["orderbook"]:
                return {"ticker": ticker, "price": orderbook[0]["orderbook"][0]["ask_price"]}
            return {"ticker": ticker, "price": None}
        except Exception as e:
            logger.error(f"Error fetching ticker price for {ticker}: {e}")
            raise
        
    @classmethod
    async def get_ticker_candles(cls, ticker: str, interval: str = "1m", to: int = 0, count: int = 200):
        """
        Upbit에서 특정 티커의 캔들 데이터를 가져옵니다.
        to: UTC timestamp 초단위 → ISO8601 포맷으로 변환하여 url 파라미터로 사용
        """
        try:
            # interval 매핑 로직
            minute_intervals = {"1m", "3m", "5m", "15m", "30m", "1h", "4h", "8h"}
            if interval in minute_intervals:
                if interval == "1h":
                    minute = "60"
                elif interval == "4h":
                    minute = "240"
                else:
                    minute = interval[:-1]
                endpoint = f"/v1/candles/minutes/{minute}"
            elif interval == "1d":
                endpoint = "/v1/candles/days"
            elif interval == "1w":
                endpoint = "/v1/candles/weeks"
            else:
                raise ValueError(f"Unsupported interval: {interval}")

            url = f"{cls.server_url}{endpoint}?market=KRW-{ticker}&count={count}"
            if to:
                iso_to = datetime.fromtimestamp(to, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                url += f"&to={iso_to}"
            headers = {"accept": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as res:
                    if res.status != 200:
                        raise Exception(f"Upbit API Error: {res.status} - {await res.text()}")
                    candles = await res.json()
                    return [
                        {
                            "timestamp": int(datetime.strptime(candle["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()),
                            "open": candle["opening_price"],
                            "high": candle["high_price"],
                            "low": candle["low_price"],
                            "close": candle["trade_price"],
                            "volume": candle["candle_acc_trade_volume"]
                        }
                        for candle in candles
                    ]
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching candles for {ticker}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while fetching candles for {ticker}: {e}")
            raise

    async def get_depo_with_pos_tickers(self):
        """
        Upbit에서 입출금 상태정보를 포함한 모든 티커 정보를 가져옵니다.

        Returns:
            dict: 티커 정보 (각 티커의 상세 정보가 포함된 딕셔너리)

        Raises:
            Exception: API 호출 실패 시 발생하는 예외
        """
        try:
            payload = {
                'access_key': self.api_key,
                'nonce': str(uuid.uuid4()),
            }

            jwt_token = jwt.encode(payload, self.secret_key)
            authorization = f"Bearer {jwt_token}"
            headers = {
                'Authorization': authorization,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/v1/status/wallet", headers=headers) as res:
                    if res.status != 200:
                        raise Exception(f"Upbit API Error: {res.status} - {await res.text()}")
                    
                    dep_withdraw_pos_tickers = filter(
                        lambda x: x['wallet_state'] == 'working',
                        await res.json()
                    )
                    processed_tickers = map(
                        lambda x: x["currency"],
                        dep_withdraw_pos_tickers
                    )
                    return list(set(processed_tickers))
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching deposit/withdrawal tickers: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while fetching deposit/withdrawal tickers: {e}")
            raise

    async def order(self, ticker: str, side: str, seed: float, size: float = 0):
        """
        Upbit에서 지정가 주문을 실행합니다.

        Args:
            ticker (str): 티커 이름 (예: "BTC")
            side (str): 주문 방향 ("bid" 또는 "ask")
            price (float): 주문 가격
            size (float): 주문 수량

        Returns:
            dict: 주문 결과 정보

        Raises:
            Exception: API 호출 실패 시 발생하는 예외
        """
        try:
            obj = {
                'market': f'KRW-{ticker}',
                'side': side,
                'identifier': str(uuid.uuid4())
            }
            
            # 시장가 매수
            if side == 'bid':
                obj['ord_type'] = 'price'
                obj['price'] = str(seed)
                
            # 시장가 매도
            elif side == 'ask':
                obj['ord_type'] = 'market'
                obj['volume'] = str(size)
            else:
                raise ValueError("Invalid side: must be 'bid' or 'ask'")
            
            query_string = unquote(urlencode(obj, doseq=True)).encode("utf-8")
            
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()

            payload = {
                'access_key': self.api_key,
                'nonce': str(uuid.uuid4()),
                'query_hash': query_hash,
                'query_hash_alg': 'SHA512',
            }

            jwt_token = jwt.encode(payload, self.secret_key)
            authorization = f"Bearer {jwt_token}"
            headers = {
                'Authorization': authorization,
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.server_url}/v1/orders", json=obj, headers=headers) as res:
                    if res.status != 201:
                        raise Exception(f"Upbit API Error: {res.status} - {await res.text()}")
                    return await res.json()
        except aiohttp.ClientError as e:
            logger.error(f"Network error while placing order for {ticker}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while placing order for {ticker}: {e}")
            raise
        
    async def get_orders(self, symbol: str, order_id: str):
        """
        Upbit에서 주문 정보를 가져옵니다.

        Returns:
            list[dict]: 주문 정보 리스트

        Raises:
            Exception: API 호출 실패 시 발생하는 예외
        """
        try:
            params = {
                'market': f'KRW-{symbol}',
                'uuids[]': [order_id]
            }
            
            query_string = unquote(urlencode(params, doseq=True)).encode("utf-8")
            
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            
            payload = {
                'access_key': self.api_key,
                'nonce': str(uuid.uuid4()),
                'query_hash': query_hash,
                'query_hash_alg': 'SHA512',
            }
            
            jwt_token = jwt.encode(payload, self.secret_key)
            authorization = f"Bearer {jwt_token}"
            headers = {
                'Authorization': authorization,
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/v1/orders/uuids", params=params, headers=headers) as res:
                    if res.status != 200:
                        raise Exception(f"Upbit API Error: {res.status} - {await res.text()}")
                    return await res.json()
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching accounts: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while fetching accounts: {e}")
            raise