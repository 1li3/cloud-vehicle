import httpx
import asyncio

async def test_server():
    # 创建异步客户端，禁用证书验证
    async with httpx.AsyncClient(verify=False) as client:
        try:
            # 发送POST请求到/demo/string端点
            response = await client.post(
                'https://localhost:6121/demo/string',
                json={'key': 'test', 'value': 'hello'},
                timeout=10.0
            )
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(test_server())