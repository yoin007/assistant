from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from data_api.routers import datas_api

app = FastAPI()

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源，生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(datas_api.router, prefix="/api")

@app.get("/api/")
async def root():
    return {"message": "Welcome to Class Data Display System API"}

# 添加健康检查端点
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8123)  # 监听所有网络接口
