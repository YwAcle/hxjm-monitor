package edu.cqupt.hxjm.devices;

import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.socket.*;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

/** Extracted /control protocol from the existing remote_service.py. No robot SDK or replay. */
@org.springframework.stereotype.Component
public class M20RouteAdapter implements DeviceAdapter {
    public String code(){return "m20_route";}
    public Map<String,Object> describe(){Map<String,Object> d=new LinkedHashMap<>();d.put("adapter",code());d.put("operations",Arrays.asList("route.start","device.status","route.stop"));d.put("external_task_id_supported",false);return d;}
    public void validate(String endpoint,String operation){
        if(!Arrays.asList("route.start","device.status","route.stop").contains(operation)){throw new IllegalArgumentException("Unsupported M20 operation");}
        java.net.URI uri=java.net.URI.create(endpoint);
        if(!Arrays.asList("ws","wss").contains(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||!"/control".equals(uri.getPath())||uri.getQuery()!=null||uri.getFragment()!=null){throw new IllegalArgumentException("M20 /control URL required");}
    }
    public Map<String,Object> submit(String run,String endpoint,String operation,Map<String,Object> payload){validate(endpoint,operation);return submitOperation(run,endpoint,operation,payload,false);}

    private static final ObjectMapper JSON=new ObjectMapper();
    private final Map<String,Exchange> exchanges=new ConcurrentHashMap<>();
    private final Set<String> reservedEndpoints=ConcurrentHashMap.newKeySet();
    private static class Exchange extends TextWebSocketHandler {
        final String id,route,url,operation; final boolean simulated;
        volatile boolean accepted,terminal;
        boolean reserved;
        volatile Map<String,Object> result;
        WebSocketSession session;
        Exchange(String id,String route,String url,boolean simulated,String operation){this.id=id;this.route=route;this.url=url;this.simulated=simulated;this.operation=operation;result=state("running",null);}
        Map<String,Object> state(String state,String error){
            Map<String,Object> r=new LinkedHashMap<>();r.put("state",state);r.put("operation",operation);r.put("simulated",simulated);
            r.put("external_task_id",null);r.put("protocol_request_id",id);r.put("route",route);r.put("error_code",error);
            return r;
        }
        synchronized void unknown(){if(!terminal){result=state("unknown","REMOTE_OUTCOME_UNKNOWN");terminal=true;}}
        @Override public synchronized void handleTextMessage(WebSocketSession session,TextMessage message) throws Exception {
            if(terminal){return;}
            Map<String,Object> data=JSON.readValue(message.getPayload(),Map.class);
            if("response".equals(data.get("type"))&&id.equals(data.get("request_id"))){
                if("device.status".equals(operation)){if(!Arrays.asList("idle","starting","running","stopping","succeeded","failed","stopped","unavailable").contains(data.get("state"))){unknown();return;}result=state("succeeded",null);result.put("device_state",data.get("state"));result.put("snapshot",data);terminal=true;return;}
                if(!Boolean.TRUE.equals(data.get("ok"))){result=state("failed","DEVICE_REJECTED");result.put("message",data.get("error"));terminal=true;}
                else{accepted=true;result=state("running",null);}
            }
            if(accepted&&("status".equals(data.get("type"))||("response".equals(data.get("type"))&&id.equals(data.get("request_id"))&&Boolean.TRUE.equals(data.get("ok"))))){
                String state=String.valueOf(data.get("state"));
                if("route.start".equals(operation)&&!route.equals(data.get("route"))){unknown();return;}
                if(Arrays.asList("succeeded","failed","stopped","idle").contains(state)){
                    result=state(("route.stop".equals(operation)||"succeeded".equals(state))?"succeeded":"failed",("route.stop".equals(operation)||"succeeded".equals(state))?null:"DEVICE_EXECUTION_FAILED");terminal=true;
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
        return submitOperation(run,url,"route.start",Collections.singletonMap("route",route),simulated);
    }
    protected Map<String,Object> submitOperation(String run,String url,String operation,Map<String,Object> payload,boolean simulated){
        String route=payload.get("route")==null?null:String.valueOf(payload.get("route"));
        Map<String,Object> command;
        if("route.start".equals(operation)){command=command(run,route);}
        else{command=new LinkedHashMap<>();command.put("action","device.status".equals(operation)?"status":"stop");command.put("request_id",run);}
        if(exchanges.containsKey(run)){throw new IllegalStateException("Run already submitted");}
        Exchange e=new Exchange(run,route,url,simulated,operation);
        exchanges.put(run,e);
        if("route.start".equals(operation)&&!reservedEndpoints.add(url)){e.result=e.state("failed","DEVICE_BUSY");e.terminal=true;return e.result;}
        e.reserved="route.start".equals(operation);
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
        if(e.simulated&&!e.terminal){e.result=e.state("succeeded",null);e.result.put("device_state","simulated");e.terminal=true;}
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
