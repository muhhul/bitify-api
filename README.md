# bitify-api

## tutorial
1. 
```
docker build -t bitify-api .
```

2. 
```
docker run --name bitify-api -d -p 8000:8000 `
  -e ALLOWED_ORIGINS="http://localhost:5173,http://localhost:3000" `
  bitify-api
```