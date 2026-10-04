package main

import (
	"sort"
	"sync"
)

type Supplier struct {
	Name string `json:"name"`
}

type Item struct {
	SKU       string    `json:"sku"`
	Name      string    `json:"name"`
	Stock     int32     `json:"stock"`
	Reserved  int32     `json:"reserved"`
	Locations []string  `json:"locations"`
	Supplier  *Supplier `json:"supplier"`
}

type Store struct {
	mu    sync.RWMutex
	items map[string]*Item
}

func NewStore() *Store {
	return &Store{items: make(map[string]*Item)}
}

func (s *Store) Put(item *Item) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.items[item.SKU] = item
}

func (s *Store) Get(sku string) *Item {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.items[sku]
}

func (s *Store) All() []*Item {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]*Item, 0, len(s.items))
	for _, item := range s.items {
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].SKU < items[j].SKU
	})
	return items
}

func (s *Store) Reset() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.items = make(map[string]*Item)
}
