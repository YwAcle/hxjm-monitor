import asyncio
import websockets
import json

async def test():
    uri = "ws://localhost:8089/ws/results"
    async with websockets.connect(uri, max_size=None) as websocket:
        # Test Ping
        print("Sending Ping...")
        await websocket.send(json.dumps({"type": "ping"}))
        # Wait a bit
        await asyncio.sleep(1)
        
        # Test Get Results
        print("Sending Get Results...")
        await websocket.send(json.dumps({"type": "get_results"}))
        
        response = await websocket.recv()
        data = json.loads(response)
        
        if "Results" in data:
            print(f"Received {len(data['Results'])} results")
            if len(data['Results']) > 0:
                first = data['Results'][0]
                print(f"First result ID: {first.get('id')}")
                print(f"Origin Face len: {len(first.get('origin_face', ''))}")
                print(f"Timestamp: {first.get('timestamp')}")
        else:
            print("Invalid response format")

if __name__ == "__main__":
    asyncio.run(test())
