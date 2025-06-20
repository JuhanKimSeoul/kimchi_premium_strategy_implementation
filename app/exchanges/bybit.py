import logging
import aiohttp
from .base import Exchange

logger = logging.getLogger(__name__)

class BybitExchange(Exchange):
    """
    Bybit 거래소 API와 상호작용하기 위한 클래스.

    이 클래스는 시장 데이터를 가져오고 Bybit의 거래 서비스를 이용하기 위한 메서드를 제공합니다.

    속성:
        client (HTTP): Bybit 통합 거래 HTTP 클라이언트 인스턴스.
    """
    name = "bybit"
    server_url = "https://api.bybit.com"
    
    async def get_tickers(self):
        """
        Bybit에서 USDT 티커 목록을 가져옵니다.

        Returns:
            list[str]: USDT 티커 목록 (USDT 접미사가 제거된 티커 이름 리스트)

        Raises:
            Exception: API 호출 실패 시 발생하는 예외
        """
        try:
            url = f"{self.server_url}/v5/market/tickers?category=linear&baseCoin=USDT"
            headers = {"accept": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as res:
                    if res.status != 200:
                        raise Exception(f"Bybit API Error: {res.status} - {await res.text()}")

                    response = await res.json()
                    if response.get("retCode") == 0:  # 성공 코드 확인
                        usdt_tickers = filter(
                            lambda x: x['symbol'].endswith('USDT'),
                            response.get("result", {}).get("list", [])
                        )
                        processed_tickers = map(
                            lambda x: x['symbol'].replace('USDT', ''),
                            usdt_tickers
                        )
                        return list(processed_tickers)
                    raise Exception(f"Bybit API Error: {response.get('retMsg')}")
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching tickers: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while fetching tickers: {e}")
            raise
        
    async def get_orderbook(self, ticker: str):
        """
        Bybit에서 특정 티커의 주문서를 가져옵니다.

        Args:
            ticker (str): 티커 이름 (예: 'BTC')

        Returns:
            dict: 표준화된 주문서 정보

        Raises:
            Exception: API 호출 실패 시 발생하는 예외
        """
        try:
            url = f"{self.server_url}/v5/market/orderbook?category=linear&symbol={ticker}USDT"
            headers = {"accept": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as res:
                    if res.status != 200:
                        raise Exception(f"Bybit API Error: {res.status} - {await res.text()}")

                    response = await res.json()
                    if response.get("retCode") == 0:
                        orderbook_data = response["result"]
                        standardized_orderbook = {
                            "ticker": ticker,
                            "timestamp": orderbook_data["ts"],
                            "orderbook": [
                                {
                                    "ask_price": float(ask[0]),
                                    "bid_price": float(bid[0]),
                                    "ask_size": float(ask[1]),
                                    "bid_size": float(bid[1])
                                }
                                for ask, bid in zip(orderbook_data["a"], orderbook_data["b"])
                            ]
                        }
                        return standardized_orderbook
                    raise Exception(f"Bybit API Error: {response.get('retMsg')}")
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching orderbook for {ticker}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while fetching orderbook for {ticker}: {e}")
            raise