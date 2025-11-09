# community.py
import asyncio
import json
import logging
import math
import os
import signal
import sys
from collections import defaultdict
from typing import Dict, List, Optional

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import (
    DataReceived,
    H3Event,
    HeadersReceived,
)
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent
from aioquic.tls import SessionTicket

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("community")

# 模拟Go代码中的数据结构
class Data:
    def __init__(self, **kwargs):
        self.Name = kwargs.get("Name", "")
        self.IP = kwargs.get("IP", "")
        self.Port = kwargs.get("Port", 0)
        self.X = kwargs.get("X", 0.0)
        self.Y = kwargs.get("Y", 0.0)
        self.Psi = kwargs.get("Psi", 0.0)
        self.Stop_label = kwargs.get("Stop_label", False)
        self.Req_Resp = kwargs.get("Req_Resp", False)
        self.V = kwargs.get("V", 0.0)
        self.W = kwargs.get("W", 0.0)
        self.Path_Param = kwargs.get("Path_Param", [])

    def to_dict(self):
        return {
            "Name": self.Name,
            "IP": self.IP,
            "Port": self.Port,
            "X": self.X,
            "Y": self.Y,
            "Psi": self.Psi,
            "Stop_label": self.Stop_label,
            "Req_Resp": self.Req_Resp,
            "V": self.V,
            "W": self.W,
            "Path_Param": self.Path_Param
        }

# 模拟Go代码中的mockDataStore
mock_data_store = defaultdict(dict)

class HttpRequestHandler:
    def __init__(self):
        self.method = ""
        self.path = ""
        self.headers = {}
        self.body = b""
        self.stream_ended = False

    def add_headers(self, headers):
        """添加请求头"""
        for header, value in headers:
            if header == b":method":
                self.method = value.decode()
            elif header == b":path":
                self.path = value.decode()
            else:
                # 存储其他头信息
                self.headers[header.decode()] = value.decode()

    def add_data(self, data: bytes, stream_ended: bool):
        """添加请求体数据"""
        self.body += data
        self.stream_ended = stream_ended

    def is_complete(self):
        """检查请求是否完整"""
        return self.stream_ended

    async def handle_request(self, protocol, stream_id):
        """处理HTTP请求"""
        if not self.is_complete():
            logger.error(f"Request not complete for stream {stream_id}")
            return

        if self.method != "POST":
            await self.send_error(protocol, stream_id, 405, "Only POST method is supported")
            return

        if self.path == "/demo/hash":
            await self.handle_demo_hash(protocol, stream_id)
        elif self.path == "/demo/string":
            await self.handle_demo_string(protocol, stream_id)
        else:
            await self.send_error(protocol, stream_id, 404, "Not Found")

    async def handle_demo_hash(self, protocol, stream_id):
        """处理 /demo/hash 端点"""
        try:
            # 解析JSON数据
            message_data = json.loads(self.body.decode())
            message = Data(**message_data)
            
            logger.info(f"message.x: {message.X}")
            logger.info("Storing data in mock store:")
            
            # 记录所有字段
            for field_name, field_value in message.to_dict().items():
                logger.info(f"Field '{field_name}': {field_value}")

            # 创建响应数据
            response = Data(**message_data)
            response.V = 1.0
            response.W = 0.5

            # 发送JSON响应
            await self.send_json_response(protocol, stream_id, response.to_dict())
            
        except json.JSONDecodeError as e:
            await self.send_error(protocol, stream_id, 400, "Invalid JSON data")
        except Exception as e:
            logger.error(f"Error in /demo/hash: {e}")
            await self.send_error(protocol, stream_id, 500, "Internal Server Error")

    async def handle_demo_string(self, protocol, stream_id):
        """处理 /demo/string 端点"""
        try:
            # 解析JSON数据
            body_data = json.loads(self.body.decode())
            body_obj = Data(**body_data)
            
            logger.info(f"Req from: {body_obj.Name}")

            # 模拟在clouder_list中增加对象
            list_key = "clouder_list"
            if list_key in mock_data_store:
                clouder_list = mock_data_store[list_key]
                if body_obj.Name not in clouder_list:
                    clouder_list[body_obj.Name] = True
                    logger.info(f"Add '{body_obj.Name}' to clouder_list")
            else:
                mock_data_store[list_key] = {body_obj.Name: True}
                logger.info(f"Add '{body_obj.Name}' to clouder_list")

            # 存储请求体
            mock_data_store[body_obj.Name] = self.body.decode()
            logger.info(f"Request Body: {self.body.decode()}")

            # 检查命令键
            command_key = f"{body_obj.Name}-c"
            check_command_result = Data()
            
            if command_key in mock_data_store:
                car_command = mock_data_store[command_key]
                check_command_result = Data(**json.loads(car_command))
                
                if check_command_result.Req_Resp:
                    logger.info(f"Command: {car_command}")
                    check_command_result.Req_Resp = False
                    command_ready_label_false = json.dumps(check_command_result.to_dict())
                    mock_data_store[command_key] = command_ready_label_false
                else:
                    logger.info("No new command available, using current data")
            else:
                mock_data_store[command_key] = self.body.decode()
                logger.info(f"{body_obj.Name} First connection")

            # 准备响应数据
            if command_key in mock_data_store:
                response_data = json.loads(mock_data_store[command_key])
                response = Data(**response_data)
            else:
                response = body_obj

            # 生成路径参数
            response.Path_Param = self.generate_straight_path(
                body_obj.X, body_obj.Y, body_obj.Psi, 20
            )
            
            logger.info(f"Generated path with {len(response.Path_Param)//2} points, "
                       f"starting at ({body_obj.X:.2f}, {body_obj.Y:.2f}), "
                       f"direction: {body_obj.Psi:.2f} radians")

            # 发送响应
            await self.send_json_response(protocol, stream_id, response.to_dict())

        except json.JSONDecodeError as e:
            await self.send_error(protocol, stream_id, 400, "Invalid JSON data")
        except Exception as e:
            logger.error(f"Error in /demo/string: {e}")
            await self.send_error(protocol, stream_id, 500, "Internal Server Error")

    def generate_straight_path(self, current_x: float, current_y: float, 
                             heading: float, point_count: int) -> List[float]:
        """生成直线路径，与Go版本保持一致"""
        path = [0.0] * (point_count * 2)
        path[0] = current_x
        path[1] = current_y
        
        step_size = 1.0
        
        for i in range(1, point_count):
            step_distance = float(i) * step_size
            x_offset = step_distance * math.cos(heading)
            y_offset = step_distance * math.sin(heading)
            
            path[2*i] = current_x + x_offset
            path[2*i+1] = current_y + y_offset
        
        return path

    async def send_json_response(self, protocol, stream_id, data: dict):
        """发送JSON响应"""
        response_body = json.dumps(data).encode()
        headers = [
            (b":status", b"200"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(response_body)).encode()),
        ]
        
        protocol._http.send_headers(
            stream_id=stream_id,
            headers=headers,
        )
        protocol._http.send_data(
            stream_id=stream_id,
            data=response_body,
            end_stream=True
        )

    async def send_error(self, protocol, stream_id, status_code: int, message: str):
        """发送错误响应"""
        error_data = {"error": message}
        response_body = json.dumps(error_data).encode()
        headers = [
            (b":status", str(status_code).encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(response_body)).encode()),
        ]
        
        protocol._http.send_headers(
            stream_id=stream_id,
            headers=headers,
        )
        protocol._http.send_data(
            stream_id=stream_id,
            data=response_body,
            end_stream=True
        )

class Http3ServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http = None
        self._handlers = {}  # 存储每个流的处理器

    def quic_event_received(self, event: QuicEvent):
        if self._http is None:
            self._http = H3Connection(self._quic)
        
        # 将QUIC事件传递给HTTP/3层
        for h3_event in self._http.handle_event(event):
            self.h3_event_received(h3_event)

    def h3_event_received(self, event: H3Event):
        if isinstance(event, HeadersReceived):
            self.handle_headers(event)
        elif isinstance(event, DataReceived):
            self.handle_data(event)

    def handle_headers(self, event: HeadersReceived):
        """处理HTTP头"""
        stream_id = event.stream_id
        
        # 为新的流创建处理器
        if stream_id not in self._handlers:
            self._handlers[stream_id] = HttpRequestHandler()
        
        handler = self._handlers[stream_id]
        handler.add_headers(event.headers)
        
        # 如果流已经结束（没有请求体），立即处理请求
        if event.stream_ended:
            handler.add_data(b"", True)
            asyncio.create_task(self.process_request(stream_id))

    def handle_data(self, event: DataReceived):
        """处理HTTP数据"""
        stream_id = event.stream_id
        
        if stream_id not in self._handlers:
            logger.warning(f"Received data for unknown stream {stream_id}")
            return
        
        handler = self._handlers[stream_id]
        handler.add_data(event.data, event.stream_ended)
        
        # 如果流结束，处理请求
        if event.stream_ended:
            asyncio.create_task(self.process_request(stream_id))

    async def process_request(self, stream_id: int):
        """处理完整的HTTP请求"""
        if stream_id not in self._handlers:
            return
        
        handler = self._handlers[stream_id]
        
        try:
            await handler.handle_request(self, stream_id)
        except Exception as e:
            logger.error(f"Error processing request for stream {stream_id}: {e}")
        finally:
            # 清理处理器
            del self._handlers[stream_id]

async def run_server(
    host: str = "0.0.0.0",
    port: int = 6121,
    certificate: str = "certpath/cert.pem",
    private_key: str = "certpath/priv.key",
):
    """运行HTTP/3服务器"""
    
    # 检查证书文件是否存在
    if not os.path.exists(certificate) or not os.path.exists(private_key):
        logger.error(f"Certificate files not found: {certificate}, {private_key}")
        logger.info("Please generate certificates first")
        return

    # 配置QUIC
    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN,
        is_client=False,
        max_datagram_frame_size=65536,
    )
    
    configuration.load_cert_chain(certificate, private_key)

    # 启动服务器
    server = await serve(
        host=host,
        port=port,
        configuration=configuration,
        create_protocol=Http3ServerProtocol,
    )
    
    logger.info(f"HTTP/3 server listening on https://{host}:{port}")
    
    try:
        await asyncio.Future()  # 永久运行
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    finally:
        server.close()

def signal_handler():
    """处理退出信号"""
    logger.info("Shutting down server...")
    # 清理模拟数据存储（可选）
    mock_data_store.clear()
    logger.info("Mock data store cleared")
    sys.exit(0)

if __name__ == "__main__":
    # 设置信号处理
    signal.signal(signal.SIGINT, lambda s, f: signal_handler())
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
    
    # 运行服务器
    asyncio.run(run_server())