// go build comm.go
// ./comm
package main

import (
	//"crypto/md5"
	//"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"math" // 使用标准库的math包进行三角函数计算
	"os"
	"os/signal"
	"reflect"
	"syscall"

	//"mime/multipart"
	//"context"
	"encoding/json" // 用于解析和返回 JSON
	"net/http"
	"strconv"
	"strings"
	"sync"

	_ "net/http/pprof"

	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/http3"

	// "github.com/quic-go/quic-go/internal/testdata"
	"github.com/quic-go/quic-go/qlog"
	// 屏蔽Redis依赖
	//"github.com/redis/go-redis/v9"
	//"github.com/quic-go/quic-go/logging"
)

type binds []string

// 定义数据传输格式，服务端客户端须保持一致
type Data struct {
	Name       string    `json:"Name"`
	IP         string    `json:"IP"`
	Port       int       `json:"Port"`
	X          float64   `json:"X"`
	Y          float64   `json:"Y"`
	Psi        float64   `json:"Psi"`
	Stop_label bool      `json:"Stop_label"`
	Req_Resp   bool      `json:"Req_Resp"`
	V          float64   `json:"V"`
	W          float64   `json:"W"`
	Path_Param []float64 `json:"Path_Param"` // 等价于C++中的std::vector<double>
}

func (b binds) String() string {
	return strings.Join(b, ",")
}

func (b *binds) Set(v string) error {
	*b = strings.Split(v, ",")
	return nil
}

// Size is needed by the /demo/upload handler to determine the size of the uploaded file
// type Size interface {
//  Size() int64
// }

// 在结构体中存储数据，用于模拟Redis
var mockDataStore sync.Map

// See https://en.wikipedia.org/wiki/Lehmer_random_number_generator
func generatePRData(l int) []byte {
	res := make([]byte, l)
	seed := uint64(1)
	for i := 0; i < l; i++ {
		seed = seed * 48271 % 2147483647
		res[i] = byte(seed)
	}
	return res
}

// 模拟删除键的函数
func deleteKeys() {
	log.Println("Deleting mock data store keys...")
	mockDataStore.Range(func(key, value interface{}) bool {
		mockDataStore.Delete(key)
		return true
	})
	log.Println("Mock data store cleared")
}

// generateStraightPath 根据当前位置、朝向生成向斜前方的直线轨迹
// 参数：
//   currentX, currentY - 当前位置坐标
//   heading - 车辆朝向（弧度制，0度为x轴正方向）
//   pointCount - 需要生成的轨迹点数量
// 返回值：
//   格式为 [X1, Y1, X2, Y2, ...] 的轨迹点切片，每个点占两个元素
func generateStraightPath(currentX, currentY, heading float64, pointCount int) []float64 {
	// 创建轨迹点数组，每个点需要2个float64值（X和Y）
	path := make([]float64, pointCount*2)
	
	// 设置起始点为当前位置
	path[0] = currentX
	path[1] = currentY
	
	// 计算每个点之间的步长，使用固定步长使轨迹呈直线
	stepSize := 1.0 // 可以根据需要调整步长
	
	// 从第二个点开始计算
	for i := 1; i < pointCount; i++ {
		// 计算沿朝向方向的偏移量
		stepDistance := float64(i) * stepSize
		
		// 根据朝向计算新点的坐标
		// 朝向为0度时，车辆朝向x轴正方向
		// 角度增加时，逆时针旋转
		xOffset := stepDistance * math.Cos(heading)
		yOffset := stepDistance * math.Sin(heading)
		
		// 设置轨迹点
		path[2*i] = currentX + xOffset
		path[2*i+1] = currentY + yOffset
	}
	
	return path
}

func setupHandler(www string) http.Handler {

	mux := http.NewServeMux()
	// ctx 不再需要，因为我们已经屏蔽了Redis依赖

	if len(www) > 0 {
		mux.Handle("/", http.FileServer(http.Dir(www)))
	} else {
		mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
			fmt.Printf("%#v\n", r)
			const maxSize = 1 << 30 // 1 GB
			num, err := strconv.ParseInt(strings.ReplaceAll(r.RequestURI, "/", ""), 10, 64)
			if err != nil || num <= 0 || num > maxSize {
				w.WriteHeader(400)
				return
			}
			w.Write(generatePRData(int(num)))
		})
	}

	mux.HandleFunc("/demo/hash", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Only POST method is supported", http.StatusMethodNotAllowed)
			return
		}
		//解析请求体中的 JSON 数据为struct
		var message Data

		err := json.NewDecoder(r.Body).Decode(&message)
		if err != nil {
			http.Error(w, "Invalid JSON data", http.StatusBadRequest)
			fmt.Printf("Error decoding JSON: %v\n", err)
			return
		}
		fmt.Printf("message.x: %v\n", message.X)

		// 模拟存储数据，将数据存入map
		value := reflect.ValueOf(message)
		typeOf := reflect.TypeOf(message)
		log.Println("Storing data in mock store:")
		for i := 0; i < value.NumField(); i++ {
			fieldName := typeOf.Field(i).Name
			fieldValue := value.Field(i).Interface()
			log.Printf("Field '%s': %v\n", fieldName, fieldValue)
		}

		// 模拟返回数据
		var response Data = message
		// 设置一些模拟的返回值
		response.V = 1.0
		response.W = 0.5

		// 返回相同的 JSON 数据
		w.Header().Set("Content-Type", "application/json")
		err = json.NewEncoder(w).Encode(response)
		if err != nil {
			http.Error(w, "Failed to encode response", http.StatusInternalServerError)
			fmt.Printf("Error encoding JSON: %v\n", err)
		}

	})

	mux.HandleFunc("/demo/string", func(w http.ResponseWriter, r *http.Request) {

		// 只接受 POST 请求
		if r.Method != http.MethodPost {
			http.Error(w, "Only POST method is supported", http.StatusMethodNotAllowed)
			return
		}

		// 读取请求体并解析为字节切片
		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "Failed to read request body", http.StatusBadRequest)
			return
		}

		// 解析 JSON 数据为结构体
		var bodyData Data
		var check_command_result Data
		err = json.Unmarshal(bodyBytes, &bodyData)
		if err != nil {
			http.Error(w, "Invalid JSON data", http.StatusBadRequest)
			fmt.Printf("Error decoding JSON: %v\n", err)
			return
		}

		fmt.Printf("Req from: %v\n", bodyData.Name)

		// 模拟在clouder_list中增加对象
		log.Printf("Processing request from: %v\n", bodyData.Name)
		// 检查是否已存在
		listKey := "clouder_list"
		if listData, ok := mockDataStore.Load(listKey); ok {
			if list, ok := listData.(map[string]bool); ok {
				if !list[bodyData.Name] {
					list[bodyData.Name] = true
					mockDataStore.Store(listKey, list)
					fmt.Printf("Add '%s' to clouder_list\n", bodyData.Name)
				}
			}
		} else {
			// 创建新的列表
			newList := map[string]bool{bodyData.Name: true}
			mockDataStore.Store(listKey, newList)
			fmt.Printf("Add '%s' to clouder_list\n", bodyData.Name)
		}

		// 模拟将请求body字符串存入存储，键名为 bodyData.Name
		bodyString := string(bodyBytes)
		mockDataStore.Store(bodyData.Name, bodyString)
		fmt.Println("Request Body:", bodyString)

		// 模拟获取键"carX-c"command的值
		commandKey := bodyData.Name + "-c"
		carcommandData, exists := mockDataStore.Load(commandKey)
		if !exists {
			// 如果键不存在，设置键值
			mockDataStore.Store(commandKey, bodyString)
			fmt.Printf("%s First connection\n", bodyData.Name)
		} else {
			// 如果键存在，打印命令
			carcommand := carcommandData.(string)
			json.Unmarshal([]byte(carcommand), &check_command_result)
			//检查Req_Resp是否为true，将其重置为false
			if check_command_result.Req_Resp {
				log.Printf("Command: %s\n", carcommand)
				check_command_result.Req_Resp = false
				command_ready_label_false, _ := json.Marshal(check_command_result)
				// 将更新后的值存回模拟存储
				mockDataStore.Store(commandKey, string(command_ready_label_false))
			} else {
				// 模拟检查更新，但不实际等待，直接返回当前数据
				log.Println("No new command available, using current data")
			}
			// 处理完成
		}
		//获取键"car"的值
		// car, err := rdb.Get(ctx, "car").Result()
		// if err != nil {
		// 	panic(err)
		// }
		// fmt.Println("car:",car)
		//Incr"car"的值
		// newValue, err := rdb.Incr(ctx, "car").Result()
		// if err != nil {
		//     fmt.Println("Failed to increment 'car':", err)
		//     return
		// }
		//在carlist集合中增加对象car1
		// err = rdb.SAdd(ctx, "carlist", "car"+car).Err()
		// if err != nil {
		// 	fmt.Println("Failed to SADD 'carlist':", err)
		// 	return
		// }
		//获取carlist集合中所有对象
		// carlist, err := rdb.SMembers(ctx, "carlist").Result()
		// if err != nil {
		// 	fmt.Println("Failed to get members of 'carlist':", err)
		// 	return
		// }
		// fmt.Println("car:",carlist)

		//json数据的反序列化
		// var response Data
		// err = json.Unmarshal([]byte(carcommand), &response)
		//如果JSON结构不固定，可以使用 map[string]interface{} 作为动态结构：
		// var jsonData map[string]interface{}
		// err = json.Unmarshal([]byte(bodyString), &jsonData)
		// if err != nil {
		// 	fmt.Println("Error decoding JSON:", err)
		// 	return
		// }
		//fmt.Printf("Decoded JSON as map: %v\n", jsonData)

		// 处理Path_Param，生成向斜前方的直线轨迹
		// 首先解析响应数据到结构体
		var response Data
		if carcommandData, exists := mockDataStore.Load(commandKey); exists {
			json.Unmarshal([]byte(carcommandData.(string)), &response)
		} else {
			response = bodyData // 如果没有存储的命令，使用请求数据
		}
		
		// 生成轨迹点：从当前位置向斜前方延伸的直线
		response.Path_Param = generateStraightPath(bodyData.X, bodyData.Y, bodyData.Psi, 20)
		
		// 记录生成的轨迹信息
		fmt.Printf("Generated path with %d points, starting at (%.2f, %.2f), direction: %.2f radians\n", 
			len(response.Path_Param)/2, bodyData.X, bodyData.Y, bodyData.Psi)
		
		// 将更新后的响应结构体序列化为JSON并返回
		w.Header().Set("Content-Type", "application/json")
		err = json.NewEncoder(w).Encode(response)
		if err != nil {
			http.Error(w, "Failed to encode response", http.StatusInternalServerError)
			fmt.Printf("Error encoding JSON: %v\n", err)
			return
		}

		// 将结构体数据response变量 写入http响应，返回JSON 数据
		// w.Header().Set("Content-Type", "application/json")
		// err = json.NewEncoder(w).Encode(response)
		// if err != nil {
		// 	http.Error(w, "Failed to encode response", http.StatusInternalServerError)
		// 	fmt.Printf("Error encoding JSON: %v\n", err)
		// }

	})
	return mux
}

func main() {

	// 屏蔽Redis连接
	// rdb := redis.NewClient(&redis.Options{
	// 	Addr:     "192.168.100.51:30079",
	// 	Password: "", // 没有密码，默认值
	// 	DB:       0,  // 默认DB 0
	// })

	// defer profile.Start().Stop()
	go func() {
		log.Println(http.ListenAndServe("localhost:6060", nil))
	}()
	// runtime.SetBlockProfileRate(1)

	bs := binds{}
	flag.Var(&bs, "bind", "bind to")
	www := flag.String("www", "", "www data")
	tcp := flag.Bool("tcp", false, "also listen on TCP")
	key := flag.String("key", "", "TLS key (requires -cert option)")
	cert := flag.String("cert", "", "TLS certificate (requires -key option)")
	flag.Parse()

	if len(bs) == 0 {
		bs = binds{"0.0.0.0:6121"}
	}

	handler := setupHandler(*www)

	var wg sync.WaitGroup
	wg.Add(len(bs))

	var certFile, keyFile string
	if *key != "" && *cert != "" {
		keyFile = *key
		certFile = *cert
	} else {
		certFile = "certpath/cert.pem"
		keyFile = "certpath/priv.key"
	}

	for _, b := range bs {
		fmt.Println("listening on", b)
		bCap := b
		go func() {
			var err error
			if *tcp {
				err = http3.ListenAndServeTLS(bCap, certFile, keyFile, handler)
			} else {
				server := http3.Server{
					Handler: handler,
					Addr:    bCap,
					QUICConfig: &quic.Config{
						Tracer: qlog.DefaultConnectionTracer,
					},
				}
				err = server.ListenAndServeTLS(certFile, keyFile)
			}
			if err != nil {
				fmt.Println(err)
			}
			wg.Done()
		}()

		// 使用 os/signal 来捕获 SIGINT 和 SIGTERM 信号（如 Ctrl+C 或 kill）
		signalChan := make(chan os.Signal, 1)
		signal.Notify(signalChan, syscall.SIGINT, syscall.SIGTERM)

		// 等待退出信号
		sig := <-signalChan
		log.Printf("Received signal: %s. Shutting down...\n", sig)

		// 在退出前删除模拟存储中的相关键
		//deleteKeys()

		// 执行优雅退出
		log.Println("Exiting...")
		os.Exit(0) // 退出程序

	}
	wg.Wait()
}
