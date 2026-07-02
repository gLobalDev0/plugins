#!/bin/bash
# KiCad-AI API Anahtarı Sızıntı Önleme Kancası

input=$(cat)
prompt=$(echo "$input" | jq -r '.prompt // .user_message // empty')

patterns=(
  "gsk_[a-zA-Z0-9]{20,}"
)

for pattern in "${patterns[@]}"; do
  if echo "$prompt" | grep -qE "$pattern"; then
    echo '{
      "continue": false,
      "user_message": "[GÜVENLİK UYARISI] Mesajınızın içinde ham Groq API anahtarı (gsk_) tespit edildi! Güvenliğiniz için lütfen bu anahtarı kaldırıp tekrar deneyin."
    }'
    exit 0
  fi
done

echo '{ "continue": true }'
