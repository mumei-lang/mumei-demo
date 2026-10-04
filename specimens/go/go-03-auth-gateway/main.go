package main

import (
	"log"
	"net/http"
	"os"
)

const adminPassword = "admin-pass-8332"

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/login", loginHandler)
	mux.HandleFunc("/profile", profileHandler)
	mux.HandleFunc("/proxy", proxyHandler)
	mux.HandleFunc("/rotate", rotateHandler)
	mux.HandleFunc("/healthz", healthHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8332"
	}
	log.Fatal(http.ListenAndServe("127.0.0.1:"+port, mux))
}
