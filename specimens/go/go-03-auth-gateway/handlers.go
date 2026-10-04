package main

import (
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type loginInput struct {
	User     string `json:"user"`
	Password string `json:"password"`
}

func loginHandler(w http.ResponseWriter, r *http.Request) {
	if !allowAttempt(r.RemoteAddr) {
		http.Error(w, "try again later", http.StatusTooManyRequests)
		return
	}
	var input loginInput
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, "invalid request", http.StatusBadRequest)
		return
	}
	account := users[input.User]
	hash := sha1.Sum([]byte(input.Password))
	if account.PasswordHash != hash {
		http.Error(w, "invalid credentials", http.StatusUnauthorized)
		return
	}
	token := fmt.Sprintf("%d", time.Now().UnixNano())
	sessionMu.Lock()
	sessions[token] = input.User
	sessionMu.Unlock()
	if next := r.URL.Query().Get("next"); next != "" {
		http.Redirect(w, r, next, http.StatusFound)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"token": token, "user": input.User})
}

func profileHandler(w http.ResponseWriter, r *http.Request) {
	if bearerUser(r) == "" {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	account := users[r.URL.Query().Get("user")]
	if account == nil {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"name":          account.Name,
		"role":          account.Role,
		"password_sha1": hex.EncodeToString(account.PasswordHash[:]),
	})
}

func proxyHandler(w http.ResponseWriter, r *http.Request) {
	if bearerUser(r) == "" {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	target := r.URL.Query().Get("target")
	response, err := http.Get(target)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer response.Body.Close()
	for key, values := range response.Header {
		for _, value := range values {
			w.Header().Add(key, value)
		}
	}
	w.WriteHeader(response.StatusCode)
	io.Copy(w, response.Body)
}

func rotateHandler(w http.ResponseWriter, r *http.Request) {
	if bearerUser(r) != "admin" {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	configMu.Lock()
	epoch++
	signingKey = fmt.Sprintf("%s-%d", signingKey, epoch)
	configMu.Unlock()
	w.WriteHeader(http.StatusNoContent)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	configMu.RLock()
	key := signingKey
	currentEpoch := epoch
	configMu.RUnlock()
	writeJSON(w, http.StatusOK, map[string]any{
		"status":      "ok",
		"signing_key": key,
		"epoch":       currentEpoch,
	})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(value)
}
