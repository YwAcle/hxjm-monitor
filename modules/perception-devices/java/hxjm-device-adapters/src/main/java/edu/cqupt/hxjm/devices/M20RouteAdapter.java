package edu.cqupt.hxjm.devices;

import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.socket.*;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

/** Extracted /control protocol from the existing remote_service.py. No robot SDK or replay. */
public class M20RouteAdapter implements AutoCloseable {
    private static final ObjectMapper JSON=new ObjectMapper();
    private final Map<String,Exchange> exchanges=new ConcurrentHashMap<>();
    private final Set<String> reservedEndpoints=ConcurrentHashMap.newKeySet();
    private static class Exchange extends TextWebSocketHandler {
        final String id,route,url; final boolean simulated;
        volatile boolean accepted,terminal;
        boolean reserved;
        volatile Map<String,Object> result;
        WebSocketSession session;
        Exchange(String id,String route,String url,boolean simulated){this.id=id;this.route=route;this.url=url;this.simulated=simulated;result=state("running",null);}
        Map<String,Object> state(String state,String error){
            Map<String,Object> r=new LinkedHashMap<>();r.put("state",state);r.put("simulated",simulated);
            r.put("external_task_id",null);r.put("protocol_request_id",id);r.put("route",route);r.put("error_code",error);
            return r;
        }
        synchronized void unknown(){if(!terminal){result=state("unknown","REMOTE_OUTCOME_UNKNOWN");terminal=true;}}
        @Override public synchronized void handleTextMessage(WebSocketSession session,TextMessage message) throws Exception {
            if(terminal){return;}
            Map<String,Object> data=JSON.readValue(message.getPayload(),Map.class);
            if("response".equals(data.get("type"))&&id.equals(data.get("request_id"))){
                if(!Boolean.TRUE.equals(data.get("ok"))){result=state("failed","DEVICE_REJECTED");result.put("message",data.get("error"));terminal=true;}
                else{accepted=true;result=state("running",null);}
            }
            if(accepted&&("status".equals(data.get("type"))||("response".equals(data.get("type"))&&id.equals(data.get("request_id"))&&Boolean.TRUE.equals(data.get("ok"))))){
                String state=String.valueOf(data.get("state"));
                if(!route.equals(data.get("route"))){unknown();return;}
                if(Arrays.asList("succeeded","failed","stopped").contains(state)){
                    result=state("succeeded".equals(state)?"succeeded":"failed","succeeded".equals(state)?null:"DEVICE_EXECUTION_FAILED");terminal=true;
                }else if(!Arrays.asList("starting","running","stopping").contains(state)){unknown();return;}
                result.put("pid",data.get("pid"));result.put("message",data.get("message"));result.put("failure",data.get("failure"));
            }
        }
        @Override public void afterConnectionClosed(WebSocketSession s,CloseStatus status){unknown();}
        @Override public void handleTransportError(WebSocketSession s,Throwable error){unknown();}
    }
    public static Map<String,Object> command(String requestId,String route){
        if(!Arrays.asList("route1","route2","route3","route4").contains(route)){throw new IllegalArgumentException("A confirmed M20 route1..route4 mapping is required");}
        Map<String,Object> m=new LinkedHashMap<>();m.put("action","start");m.put("route",route);m.put("loops",1);m.put("request_id",requestId);return m;
    }
    public Map<String,Object> submit(String run,String url,String route,boolean simulated){
        Map<String,Object> command=command(run,route);
        if(exchanges.containsKey(run)){throw new IllegalStateException("Run already submitted");}
        Exchange e=new Exchange(run,route,url,simulated);
        exchanges.put(run,e);
        if(!reservedEndpoints.add(url)){e.result=e.state("failed","DEVICE_BUSY");e.terminal=true;return e.result;}
        e.reserved=true;
        if(simulated){e.result=e.state("running",null);return e.result;}
        try{
            e.session=new StandardWebSocketClient().doHandshake(e,url).get(5,TimeUnit.SECONDS);
            e.session.setTextMessageSizeLimit(65536);
            e.session.sendMessage(new TextMessage(JSON.writeValueAsString(command)));
        }catch(Exception uncertain){e.unknown();}
        synchronized(e){return new LinkedHashMap<>(e.result);}
    }
    public Map<String,Object> poll(String run){
        Exchange e=exchanges.get(run);
        if(e==null){Map<String,Object> r=new LinkedHashMap<>();r.put("state","unknown");r.put("error_code","DEVICE_SESSION_LOST");return r;}
        if(e.simulated&&!e.terminal){e.result=e.state("succeeded",null);e.terminal=true;}
        Map<String,Object> result;
        synchronized(e){result=new LinkedHashMap<>(e.result);}
        if(e.terminal){release(run);}
        return result;
    }
    public void release(String run){
        Exchange e=exchanges.remove(run);if(e==null){return;}
        // Unknown outcome keeps the endpoint blocked until operator reconciliation/restart, never auto-resends.
        if(e.reserved&&!"unknown".equals(e.result.get("state"))){reservedEndpoints.remove(e.url);}
        if(e.session!=null){try{e.session.close();}catch(java.io.IOException ignored){ }}
    }
    @Override public void close(){for(String run:new ArrayList<>(exchanges.keySet())){release(run);}}
}
