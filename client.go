// go build client.go
// ./client https://localhost:6121/demo/string
// go run client.go https://localhost:6121/demo/string
package main

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"flag"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"

	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/http3"

	// "github.com/quic-go/quic-go/internal/testdata"
	"github.com/quic-go/quic-go/qlog"
)

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
	Path_Param []float64 `json:"Path_Param"` // 等价于std::vector<double>
}

func main() {
	quiet := flag.Bool("q", false, "don't print the data")
	keyLogFile := flag.String("keylog", "", "key log file")
	insecure := flag.Bool("insecure", true, "skip certificate verification")
	flag.Parse()
	urls := flag.Args()

	var keyLog io.Writer
	if len(*keyLogFile) > 0 {
		f, err := os.Create(*keyLogFile)
		if err != nil {
			log.Fatal(err)
		}
		defer f.Close()
		keyLog = f
	}

	// Create certificate pool
	pool, err := x509.SystemCertPool()
	if err != nil {
		log.Fatal(err)
	}
	// testdata.AddRootCA(pool)

	// Create QUIC transport for HTTP/3
	roundTripper := &http3.Transport{
		TLSClientConfig: &tls.Config{
			RootCAs:            pool,
			InsecureSkipVerify: *insecure,
			KeyLogWriter:       keyLog,
		},
		QUICConfig: &quic.Config{
			Tracer: qlog.DefaultConnectionTracer,
		},
	}
	defer roundTripper.Close()

	// HTTP client using the QUIC transport
	hclient := &http.Client{
		Transport: roundTripper,
	}

	// Create a WaitGroup to wait for all requests
	var wg sync.WaitGroup
	wg.Add(3) // Because we are sending 3 requests

	// URLs to send requests to
	for i := 1; i <= 3; i++ {
		name := "clouder" + strconv.Itoa(i)
		data := Data{
			Name:       name,
			IP:         "192.168.196.X",
			Port:       0,
			X:          0.5,
			Y:          5,
			Psi:        0,
			Stop_label: false,
			Req_Resp:   true,
			V:          0,
			W:          0,
			Path_Param: make([]float64, 40),
		}

		// Marshal the data to JSON
		jsonData, err := json.Marshal(data)
		if err != nil {
			log.Fatal(err)
		}

		for _, addr := range urls {
			log.Printf("Sending POST request to %s", addr)
			go func(addr string, jsonData []byte) {
				defer wg.Done()

				// Create POST request with JSON data
				req, err := http.NewRequest("POST", addr, bytes.NewBuffer(jsonData))
				if err != nil {
					log.Fatal(err)
				}
				//req.Header.Set("Content-Type", "application/json")

				// Send the request
				rsp, err := hclient.Do(req)
				if err != nil {
					log.Fatal(err)
				}
				log.Printf("Got response for %s: %#v", addr, rsp)

				// Read the response body
				body := &bytes.Buffer{}
				_, err = io.Copy(body, rsp.Body)
				if err != nil {
					log.Fatal(err)
				}
				if *quiet {
					log.Printf("Response Body: %d bytes", body.Len())
				} else {
					log.Printf("Response Body (%d bytes):\n%s", body.Len(), body.Bytes())
				}
			}(addr, jsonData)
		}
	}

	// Wait for all requests to complete
	wg.Wait()
}
