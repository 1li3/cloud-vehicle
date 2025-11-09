# Python版HTTP/3服务器使用说明

本文档详细介绍如何使用Python实现的HTTP/3服务器，该服务器实现了与Go版本`comm.go`相同的功能，可以与Go客户端进行通信。

## 功能概述

Python版HTTP/3服务器实现了以下功能：

1. 支持HTTP/3协议
2. 提供与Go版本相同的API接口
3. 实现数据解析与轨迹生成
4. 使用模拟数据存储替代Redis
5. 支持TLS加密通信

## 依赖安装

在运行Python版本的服务器之前，需要安装以下依赖：

```bash
pip install hypercorn quart httpx
```

- `hypercorn`: 支持HTTP/3协议的ASGI服务器
- `quart`: 异步Web框架，与Flask API兼容
- `httpx`: 支持HTTP/3的异步HTTP客户端（如果需要测试）

## 运行步骤

1. **确保TLS证书存在**

   服务器需要TLS证书才能运行HTTP/3。请确保在项目目录下存在`certpath`文件夹，其中包含：
   - `cert.pem`: 证书文件
   - `priv.key`: 私钥文件

2. **运行服务器**

   在项目根目录执行以下命令启动Python版HTTP/3服务器：

   ```bash
   python3 comm.py
   ```

   服务器将在`0.0.0.0:6121`端口上启动，与Go版本保持一致。

## 与Go客户端通信

Python服务器实现了与Go客户端兼容的API接口，Go客户端可以直接连接到Python服务器。

### 使用示例

假设您已经有一个Go客户端（如项目中的`client.go`），可以通过以下方式连接Python服务器：

```bash
./client https://localhost:6121/demo/string
```

服务器将响应与Go版本相同格式的JSON数据，包括生成的轨迹点。

## 主要功能点

### 1. 数据结构

Python版本使用`Data`类表示与Go版本相同的数据结构：

```python
@dataclass
class Data:
    Name: str = ""
    IP: str = ""
    Port: int = 0
    X: float = 0.0
    Y: float = 0.0
    Psi: float = 0.0
    Stop_label: bool = False
    Req_Resp: bool = False
    V: float = 0.0
    W: float = 0.0
    Path_Param: List[float] = None
```

### 2. 轨迹生成

服务器实现了`generate_straight_path`函数，根据当前位置、朝向生成向斜前方的直线轨迹：

```python
def generate_straight_path(current_x, current_y, heading, point_count):
    # 创建轨迹点数组
    path = [0.0] * (point_count * 2)
    # 设置起始点
    path[0] = current_x
    path[1] = current_y
    # 生成后续点
    step_size = 1.0
    for i in range(1, point_count):
        step_distance = float(i) * step_size
        x_offset = step_distance * math.cos(heading)
        y_offset = step_distance * math.sin(heading)
        path[2*i] = current_x + x_offset
        path[2*i+1] = current_y + y_offset
    return path
```

### 3. API端点

Python服务器提供与Go版本相同的API端点：

- `GET /`: 生成指定大小的伪随机数据
- `POST /demo/hash`: 处理数据哈希请求
- `POST /demo/string`: 处理主要业务逻辑，包括轨迹生成

## 注意事项

1. **证书配置**
   - 确保TLS证书有效，否则Go客户端可能会拒绝连接
   - 如需忽略证书验证，可在Go客户端中添加相关选项

2. **数据格式兼容性**
   - 确保JSON数据格式与Go版本完全一致
   - 特别是`Path_Param`字段的处理，应保持20个位置点（40个float64值）的格式

3. **错误处理**
   - 服务器实现了基本的错误处理和日志记录
   - 可根据需要扩展错误处理逻辑

4. **并发处理**
   - Python版本使用异步处理请求，与Go版本的并发模型不同，但功能保持一致

## 代码结构

- `comm.py`: Python版HTTP/3服务器实现
  - `Data`类：数据结构定义
  - `generate_straight_path`函数：轨迹生成算法
  - API端点处理函数：`handle_root`, `handle_hash`, `handle_string`
  - 主程序逻辑：配置和启动HTTP/3服务器

## 测试方法

1. 启动Python服务器：
   ```bash
   python3 comm.py
   ```

2. 使用Go客户端发送请求：
   ```bash
   ./client https://localhost:6121/demo/string
   ```

3. 检查服务器日志，确认轨迹生成是否正常：
   ```
   Generated path with 20 points, starting at (X, Y), direction: Psi radians
   ```

4. 验证客户端接收到的响应是否包含正确格式的轨迹数据。

## 常见问题排查

1. **连接失败**
   - 检查TLS证书是否正确配置
   - 确认端口6121是否被占用
   - 验证防火墙设置是否允许该端口通信

2. **轨迹生成异常**
   - 检查请求中X、Y和Psi字段是否正确
   - 查看服务器日志中关于轨迹生成的信息

3. **性能问题**
   - 对于高性能需求，可考虑调整异步处理参数
   - 优化数据处理逻辑，减少不必要的JSON序列化/反序列化