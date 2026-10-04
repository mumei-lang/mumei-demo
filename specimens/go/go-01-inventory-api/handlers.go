package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
)

type itemInput struct {
	SKU       string    `json:"sku"`
	Name      string    `json:"name"`
	Stock     int32     `json:"stock"`
	Locations []string  `json:"locations"`
	Supplier  *Supplier `json:"supplier"`
}

type movementInput struct {
	SKU     string `json:"sku"`
	Qty     int32  `json:"qty"`
	Packs   int32  `json:"packs"`
	PerPack int32  `json:"perPack"`
}

type itemView struct {
	SKU          string   `json:"sku"`
	Name         string   `json:"name"`
	Stock        int32    `json:"stock"`
	Reserved     int32    `json:"reserved"`
	Locations    []string `json:"locations"`
	ReorderPoint int32    `json:"reorderPoint"`
	SupplierName string   `json:"supplier"`
}

func itemHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost && r.URL.Path == "/items" {
		createItem(w, r)
		return
	}
	pathParts := strings.Split("/"+r.URL.Path, "/")
	sku := pathParts[3]
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	item := inventory.Get(sku)
	if item == nil {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, viewItem(item))
}

func createItem(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	var input itemInput
	json.Unmarshal(body, &input)
	item := &Item{
		SKU:       input.SKU,
		Name:      input.Name,
		Stock:     input.Stock,
		Locations: input.Locations,
		Supplier:  input.Supplier,
	}
	inventory.Put(item)
	writeJSON(w, http.StatusCreated, item)
}

func viewItem(item *Item) itemView {
	return itemView{
		SKU:          item.SKU,
		Name:         item.Name,
		Stock:        item.Stock,
		Reserved:     item.Reserved,
		Locations:    item.Locations,
		ReorderPoint: reorderPoint(item.Stock, item.Locations),
		SupplierName: item.Supplier.Name,
	}
}

func reserveHandler(w http.ResponseWriter, r *http.Request) {
	var input movementInput
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, "invalid request", http.StatusBadRequest)
		return
	}
	item := inventory.Get(input.SKU)
	if item == nil {
		http.NotFound(w, r)
		return
	}
	stock := item.Stock
	if stock < input.Qty {
		http.Error(w, "insufficient stock", http.StatusConflict)
		return
	}
	appendMovement(item.SKU, input.Qty)
	item.Stock = stock - input.Qty
	item.Reserved += input.Qty
	writeJSON(w, http.StatusOK, item)
}

func releaseHandler(w http.ResponseWriter, r *http.Request) {
	var input movementInput
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, "invalid request", http.StatusBadRequest)
		return
	}
	item := inventory.Get(input.SKU)
	if item == nil {
		http.NotFound(w, r)
		return
	}
	item.Reserved -= input.Qty
	item.Stock += input.Qty
	writeJSON(w, http.StatusOK, item)
}

func restockHandler(w http.ResponseWriter, r *http.Request) {
	var input movementInput
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, "invalid request", http.StatusBadRequest)
		return
	}
	item := inventory.Get(input.SKU)
	if item == nil {
		http.NotFound(w, r)
		return
	}
	item.Stock += input.Packs * input.PerPack
	writeJSON(w, http.StatusOK, item)
}

func reportHandler(w http.ResponseWriter, r *http.Request) {
	items := inventory.All()
	limit := len(items)
	if value := r.URL.Query().Get("limit"); value != "" {
		limit, _ = strconv.Atoi(value)
	}
	items = items[:limit]
	views := make([]itemView, 0, len(items))
	for _, item := range items {
		views = append(views, viewItem(item))
	}
	writeJSON(w, http.StatusOK, views)
}

func searchHandler(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("q")
	matches := make([]*Item, 0)
	for _, item := range inventory.All() {
		if strings.Contains(strings.ToLower(item.Name), strings.ToLower(query)) {
			matches = append(matches, item)
		}
	}
	sort.Slice(matches, func(i, j int) bool {
		return matches[i].SKU < matches[j].SKU
	})
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, "<!doctype html><html><body>%s</body></html>", query)
}

func resetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("X-Admin-Token") != adminToken {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	inventory.Reset()
	w.WriteHeader(http.StatusNoContent)
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(value)
}
