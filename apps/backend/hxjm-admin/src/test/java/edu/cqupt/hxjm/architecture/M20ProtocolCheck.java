package edu.cqupt.hxjm.architecture;

import java.util.*;
import java.lang.reflect.*;
import edu.cqupt.hxjm.devices.M20RouteAdapter;
import org.springframework.web.socket.*;

/** Protocol replay only: no socket, robot service, SDK or hardware operation. */
public class M20ProtocolCheck {
    static void expect(boolean ok){if(!ok){throw new AssertionError("M20 protocol mismatch");}}
    public static void main(String[] args) throws Exception {
        expect(M20RouteAdapter.command("run","route1").equals(new LinkedHashMap<String,Object>(){{put("action","start");put("route","route1");put("loops",1);put("request_id","run");}}));
        try{M20RouteAdapter.command("run","pixel:100,100");throw new AssertionError();}catch(IllegalArgumentException expected){ }
        Class<?> type=Class.forName("edu.cqupt.hxjm.devices.M20RouteAdapter$Exchange");
        Constructor<?> ctor=type.getDeclaredConstructor(String.class,String.class,String.class,boolean.class,String.class);ctor.setAccessible(true);
        Object exchange=ctor.newInstance("run","route1","ws://local/control",false,"route.start");
        Method message=type.getDeclaredMethod("handleTextMessage",WebSocketSession.class,TextMessage.class);message.setAccessible(true);
        Field result=type.getDeclaredField("result");result.setAccessible(true);
        message.invoke(exchange,null,new TextMessage("{\"type\":\"status\",\"route\":\"route2\",\"state\":\"succeeded\"}"));
        expect("running".equals(((Map<?,?>)result.get(exchange)).get("state")));
        message.invoke(exchange,null,new TextMessage("{\"type\":\"response\",\"request_id\":\"run\",\"ok\":true,\"route\":\"route1\",\"state\":\"running\"}"));
        Method closed=type.getDeclaredMethod("afterConnectionClosed",WebSocketSession.class,CloseStatus.class);closed.setAccessible(true);closed.invoke(exchange,null,CloseStatus.NORMAL);
        expect("unknown".equals(((Map<?,?>)result.get(exchange)).get("state")));
        Object fast=ctor.newInstance("fast","route1","ws://local/control",false,"route.start");
        message.invoke(fast,null,new TextMessage("{\"type\":\"response\",\"request_id\":\"fast\",\"ok\":true,\"route\":\"route1\",\"state\":\"succeeded\"}"));
        expect("succeeded".equals(((Map<?,?>)result.get(fast)).get("state")));
        Object status=ctor.newInstance("status",null,"ws://local/control",false,"device.status");
        message.invoke(status,null,new TextMessage("{\"type\":\"response\",\"request_id\":\"status\",\"state\":\"running\",\"route\":\"route2\"}"));
        expect("succeeded".equals(((Map<?,?>)result.get(status)).get("state")));
        expect("running".equals(((Map<?,?>)result.get(status)).get("device_state")));
        Object stop=ctor.newInstance("stop",null,"ws://local/control",false,"route.stop");
        message.invoke(stop,null,new TextMessage("{\"type\":\"response\",\"request_id\":\"stop\",\"ok\":true,\"state\":\"stopping\"}"));
        expect("running".equals(((Map<?,?>)result.get(stop)).get("state")));
        message.invoke(stop,null,new TextMessage("{\"type\":\"status\",\"state\":\"stopped\"}"));
        expect("succeeded".equals(((Map<?,?>)result.get(stop)).get("state")));
        try(M20RouteAdapter adapter=new M20RouteAdapter()){
            adapter.submit("one","mock://local","route1",true);
            expect("DEVICE_BUSY".equals(adapter.submit("two","mock://local","route2",true).get("error_code")));
            expect("failed".equals(adapter.poll("two").get("state")));
            expect(Boolean.TRUE.equals(adapter.poll("one").get("simulated")));
            expect("unknown".equals(adapter.poll("missing").get("state")));
        }
        System.out.println("M20ProtocolCheck passed: exact demo command, no pixel navigation, initial snapshot isolation, fast completion, disconnect unknown and simulated busy; no socket opened");
    }
}
