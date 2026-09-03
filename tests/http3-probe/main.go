package main

import (
	"crypto/tls"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/quic-go/quic-go/http3"
)

func main() {
	if len(os.Args) != 5 {
		fmt.Fprintln(os.Stderr, "usage: http3-probe <server-name> <port> <path> <expected-status>")
		os.Exit(2)
	}
	serverName := os.Args[1]
	port := os.Args[2]
	path := os.Args[3]
	expected, err := strconv.Atoi(os.Args[4])
	if err != nil || expected < 100 || expected > 599 {
		fmt.Fprintln(os.Stderr, "invalid expected status")
		os.Exit(2)
	}
	transport := &http3.Transport{
		TLSClientConfig: &tls.Config{
			ServerName: serverName,
			MinVersion: tls.VersionTLS13,
		},
	}
	defer transport.Close()
	client := &http.Client{Transport: transport, Timeout: 15 * time.Second}
	requestURL := "https://127.0.0.1:" + port + path
	response, err := client.Get(requestURL)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
	if response.StatusCode != expected {
		fmt.Fprintf(os.Stderr, "expected HTTP %d, received %d\n", expected, response.StatusCode)
		os.Exit(1)
	}
	fmt.Printf("HTTP3_STATUS=%d\n", response.StatusCode)
}
