# shellcheck shell=bash
# CA locale usa-e-getta per le prove e2e (TLS reale verificato verso DB, Redis e proxy).
# Estensioni conformi a VERIFY_X509_STRICT (default da Python 3.13): CA con keyUsage,
# foglie con AKI/SKI e basicConstraints. Una CA privata di produzione deve rispettarle.
# Uso: e2e_certs <directory> <nome-db> <nome-redis>   (es. "db" "redis" in compose)
e2e_leaf() { # e2e_leaf <dir> <nome> <SAN>
  local dir=$1 name=$2 san=$3
  mkdir -p "$dir/$name"
  openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$dir/$name/key.pem" -out "$dir/$name/req.csr" -subj "/CN=$name" 2>/dev/null
  openssl x509 -req -in "$dir/$name/req.csr" -CA "$dir/ca.crt" -CAkey "$dir/ca.key" \
    -CAcreateserial -days 7 -sha256 -out "$dir/$name/cert.pem" \
    -extfile <(printf '%s\n' "subjectAltName=$san" "extendedKeyUsage=serverAuth" \
      "basicConstraints=critical,CA:FALSE" "keyUsage=critical,digitalSignature,keyEncipherment" \
      "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid,issuer") 2>/dev/null
  rm -f "$dir/$name/req.csr"
}

e2e_certs() {
  local dir=$1 db=${2:-db} redis=${3:-redis}
  mkdir -p "$dir"
  if [ ! -s "$dir/ca.crt" ]; then
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 7 \
      -keyout "$dir/ca.key" -out "$dir/ca.crt" -subj "/CN=ripetizioni-e2e-ca" \
      -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
      -addext "subjectKeyIdentifier=hash" 2>/dev/null
  fi
  e2e_leaf "$dir" db "DNS:$db,DNS:localhost,IP:127.0.0.1"
  e2e_leaf "$dir" redis "DNS:$redis,DNS:localhost,IP:127.0.0.1"
  e2e_leaf "$dir" proxy "DNS:localhost,IP:127.0.0.1"
  # Layout atteso da compose.e2e.yaml.
  cp "$dir/db/cert.pem" "$dir/db/db.crt"
  cp "$dir/db/key.pem" "$dir/db/db.key"
  cp "$dir/redis/cert.pem" "$dir/redis/redis.crt"
  cp "$dir/redis/key.pem" "$dir/redis/redis.key"
  cp "$dir/ca.crt" "$dir/redis/ca.crt"
  cat "$dir/proxy/cert.pem" "$dir/ca.crt" > "$dir/proxy/fullchain.pem"
  cp "$dir/proxy/key.pem" "$dir/proxy/privkey.pem"
  chmod 0644 "$dir"/*/*.pem "$dir"/*/*.crt "$dir"/*/*.key "$dir/ca.crt"
}

# ACL Redis con password note (solo e2e): stesso modello di infra/redis/users.acl.example.
e2e_acl() { # e2e_acl <file> <password-app>
  local hash
  hash=$(printf '%s' "$2" | sha256sum | cut -d' ' -f1)
  sed -e "s|#<sha256-della-password-app>|#$hash|" \
      -e "s|#<sha256-della-password-exporter>|#$hash|" \
      -e '/^#/d' "$(repo_root)/infra/redis/users.acl.example" > "$1"
  chmod 0644 "$1"
}
