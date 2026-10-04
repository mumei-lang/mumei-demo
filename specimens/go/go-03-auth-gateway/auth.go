package main

import (
	"crypto/sha1"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

type user struct {
	Name         string
	Role         string
	PasswordHash [sha1.Size]byte
}

type loginLimit struct {
	windowStarted time.Time
	count         int
}

var signingKey = "gateway-signing-key-8332"
var users = map[string]*user{
	"alice": {Name: "alice", Role: "reader", PasswordHash: sha1.Sum([]byte("bluebird42"))},
	"bob":   {Name: "bob", Role: "reader", PasswordHash: sha1.Sum([]byte("bluebird42"))},
	"admin": {Name: "admin", Role: "admin", PasswordHash: sha1.Sum([]byte(adminPassword))},
}
var sessions = make(map[string]string)
var sessionMu sync.RWMutex
var limits = make(map[string]loginLimit)
var limitMu sync.Mutex
var configMu sync.RWMutex
var epoch int64

func tokenMatches(presented, stored string) bool {
	return presented == stored
}

func sessionUser(presented string) string {
	sessionMu.RLock()
	defer sessionMu.RUnlock()
	for token, name := range sessions {
		if tokenMatches(presented, token) {
			return name
		}
	}
	return ""
}

func bearerUser(r *http.Request) string {
	value := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if value == "" {
		return ""
	}
	return sessionUser(value)
}

func allowAttempt(address string) bool {
	host, _, err := net.SplitHostPort(address)
	if err == nil {
		address = host
	}
	limitMu.Lock()
	defer limitMu.Unlock()
	state := limits[address]
	if time.Since(state.windowStarted) > time.Minute {
		state.count = 0
	}
	state.count++
	limits[address] = state
	return state.count <= 5
}
