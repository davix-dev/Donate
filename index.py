import asyncio
import os
import httpx
from fastapi import FastAPI, HTTPException, Query
import uvicorn

app = FastAPI()

# ================== CẤU HÌNH ==================
ROBLOX_COOKIE = os.environ.get("ROBLOX_COOKIE")
if not ROBLOX_COOKIE:
    print("WARNING: ROBLOX_COOKIE env variable is not set.")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Cookie": f".ROBLOSECURITY={ROBLOX_COOKIE}"
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
    
    async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)) as client:
        try:
            # Bước 1: Lấy danh sách Universe
            res = await client.get(f"https://games.roblox.com/v2/users/{userId}/games?sortOrder=Asc&limit=50", headers=HEADERS)
            if res.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to fetch games: {res.text}")
                
            data_json = res.json()
            games_data = data_json.get("data", [])

            # Giai đoạn 1: Lấy tất cả gamepass từ các universe (đã bao gồm price)
            tasks_uni = [fetch_game_passes(client, uni) for uni in games_data]
            results_uni = await asyncio.gather(*tasks_uni)
            
            for passes in results_uni:
                for p in passes:
                    final_results.append(p)
                    # Giới hạn tối đa 10 game pass
                    if len(final_results) >= 10:
                        break
                if len(final_results) >= 10:
                    break
        
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {"d": final_results}

if __name__ == "__main__":
    # Chạy server với Uvicorn khi file được chạy trực tiếp
    # uvicorn index:app --host 0.0.0.0 --port $PORT
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)