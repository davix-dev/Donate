import asyncio
import os
import httpx
from fastapi import FastAPI, HTTPException, Query
import uvicorn

app = FastAPI()

# ================== CẤU HÌNH ==================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

# Semaphore để giới hạn concurrency
sem = asyncio.Semaphore(10)

async def fetch_game_passes(client, uni):
    async with sem:
        try:
            u_id = uni["id"]
            p_res = await client.get(
                f"https://apis.roblox.com/game-passes/v1/universes/{u_id}/game-passes?passView=Full", 
                headers=HEADERS
            )
            if p_res.status_code != 200:
                return []
                
            data = p_res.json()
            passes = data.get("gamePasses", [])
            
            valid_passes = []
            for gp in passes:
                price = gp.get("price")
                if gp.get("isForSale") and price is not None:
                    valid_passes.append([gp["id"], price])
            return valid_passes
        except Exception:
            return []

@app.api_route("/ping", methods=["GET", "HEAD"])
async def ping():
    return "pong"

@app.get("/get-all-passes")
async def get_all_passes(userId: str = Query(..., description="The Roblox User ID")):
    if not userId:
        raise HTTPException(status_code=400, detail="Missing userId")

    final_results = []
    
    async with httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        timeout=httpx.Timeout(10.0)
    ) as client:
        try:
            # Bước 1: Lấy danh sách Universe
            res = await client.get(f"https://games.roblox.com/v2/users/{userId}/games?sortOrder=Asc&limit=50", headers=HEADERS)
            if res.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to fetch games: {res.text}")
                
            data_json = res.json()
            games_data = data_json.get("data", [])

            # Giai đoạn 1: Lấy gamepass từ các universe (dừng khi đủ 10)
            for uni in games_data:
                passes = await fetch_game_passes(client, uni)
                for p in passes:
                    final_results.append(p)
                    if len(final_results) >= 10:
                        break
                if len(final_results) >= 10:
                    break
            
            # Cắt bớt nếu thừa (trường hợp loop trong loop add dư)
            final_results = final_results[:10]
        
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {"d": final_results}

if __name__ == "__main__":
    # Chạy server với Uvicorn khi file được chạy trực tiếp
    # uvicorn index:app --host 0.0.0.0 --port $PORT
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
