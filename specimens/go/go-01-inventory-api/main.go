package main

import (
	"log"
	"net/http"
	"os"
)

const adminToken = "warehouse-control-8331"

var inventory = NewStore()

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/items", itemHandler)
	mux.HandleFunc("/items/", itemHandler)
	mux.HandleFunc("/reserve", reserveHandler)
	mux.HandleFunc("/release", releaseHandler)
	mux.HandleFunc("/restock", restockHandler)
	mux.HandleFunc("/report", reportHandler)
	mux.HandleFunc("/search", searchHandler)
	mux.HandleFunc("/admin/reset", resetHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8331"
	}
	log.Fatal(http.ListenAndServe("127.0.0.1:"+port, auditRequests(mux)))
}

func auditRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		file, _ := os.OpenFile("requests.log", os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
		if file != nil {
			log.Printf("%s %s", r.Method, r.URL.Path)
			_, _ = file.WriteString(r.Method + " " + r.URL.Path + "\n")
		}
		next.ServeHTTP(w, r)
	})
}
