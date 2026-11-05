package edu.cqupt.hxjm.algdeployment.capability.service;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import edu.cqupt.hxjm.algdeployment.business.security.BusinessAuthentication;
import static edu.cqupt.hxjm.algdeployment.business.store.BusinessValues.*;

/** One synchronous request, no redirects and no automatic replay. */
public class CapabilityHttpAdapter {
    public static class Failure extends RuntimeException {
        public final String code;
        Failure(String code) { super(code); this.code=code; }
    }
    public Object execute(Map<String,Object> operation, Map<String,Object> input, Map<String,Object> parameters,
                          BusinessAuthentication authentication) {
        HttpURLConnection connection=null;
        try {
            connection=(HttpURLConnection)new URL(text(operation,"url",2048)).openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod(text(operation,"method",16));
            connection.setConnectTimeout(((Number)operation.get("connect_timeout_ms")).intValue());
            connection.setReadTimeout(((Number)operation.get("response_timeout_ms")).intValue());
            connection.setRequestProperty("Content-Type","application/json");
            if(operation.get("credential_ref")!=null){
                String ref=operation.get("credential_ref").toString();
                connection.setRequestProperty(BusinessAuthentication.SERVICE_ID_HEADER,ref);
                connection.setRequestProperty(BusinessAuthentication.SERVICE_TOKEN_HEADER,authentication.serviceToken(ref));
            }
            Object body="payload".equals(operation.get("request_mode"))?required(input,"payload"):values("input",input,"parameters",parameters);
            byte[] bytes=json(body).getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);connection.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream out=connection.getOutputStream()){out.write(bytes);}
            int status=connection.getResponseCode();
            if(status<200||status>=300){throw new Failure("REMOTE_HTTP_ERROR");}
            ByteArrayOutputStream buffer=new ByteArrayOutputStream();
            try(InputStream in=connection.getInputStream()){
                byte[] chunk=new byte[8192];int read;
                while((read=in.read(chunk))!=-1){
                    if(buffer.size()+read>((Number)operation.get("max_response_bytes")).intValue()){throw new Failure("REMOTE_RESPONSE_TOO_LARGE");}
                    buffer.write(chunk,0,read);
                }
            }
            Object decoded;
            try { decoded=parseValue(new String(buffer.toByteArray(),StandardCharsets.UTF_8)); }
            catch(RuntimeException invalid){throw new Failure("REMOTE_INVALID_RESPONSE");}
            if("business".equals(operation.get("response_mode"))){
                Map<String,Object> response=map(decoded);
                if(response.containsKey("error")){throw new Failure("REMOTE_BUSINESS_ERROR");}
                response.remove("trace_id");
                return response;
            }
            return decoded;
        }catch(Failure known){throw known;}
        catch(IOException uncertain){throw new Failure("REMOTE_OUTCOME_UNKNOWN");}
        finally{if(connection!=null){connection.disconnect();}}
    }
}
