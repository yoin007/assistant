import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "data_api.main:app",
        host="0.0.0.0",
        port=8123,
        reload=True,
        reload_dirs=["./data_api/"],
    )
