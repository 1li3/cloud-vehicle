// go build -o http3client.so -buildmode=c-shared http3client.go
package main

import "C"
import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"io"
	"log"
	"net/http"
	"sync"

	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/http3"
)

var (
	hclient       *http.Client
	initTransport sync.Once // 确保 Transport 初始化只执行一次
)

// 初始化全局 HTTP/3 客户端
func initHTTP3Client() {
	pool, err := x509.SystemCertPool()
	if err != nil {
		log.Fatal(err)
	}
	// 可以在这里添加自定义CA，如果需要的话

	roundTripper := &http3.Transport{
		TLSClientConfig: &tls.Config{
			RootCAs:            pool,
			InsecureSkipVerify: true,
		},
		QUICConfig: &quic.Config{},
	}

	hclient = &http.Client{
		Transport: roundTripper,
	}
}

//export posthttp3
func posthttp3(Data *C.char, addr *C.char) *C.char {
	// 确保 HTTP/3 客户端初始化
	initTransport.Do(initHTTP3Client)

	data := C.GoString(Data)
	address := C.GoString(addr)
	postData := []byte(data)

	// 创建 POST 请求
	log.Printf("Post to %s", address)
	req, err := http.NewRequest("POST", address, bytes.NewBuffer(postData))
	if err != nil {
		log.Printf("Failed to create request: %v", err)
		return C.CString("Error: failed to create request")
	}

	// 发送请求
	rsp, err := hclient.Do(req)
	if err != nil {
		log.Printf("Request failed: %v", err)
		return C.CString("Error: request failed")
	}
	defer rsp.Body.Close()

	// 读取响应
	body := &bytes.Buffer{}
	_, err = io.Copy(body, rsp.Body)
	if err != nil {
		log.Printf("Failed to read response: %v", err)
		return C.CString("Error: failed to read response")
	}

	log.Printf("Response (%d bytes): %s", body.Len(), body.Bytes())
	return C.CString(body.String())
}

func main() {}
