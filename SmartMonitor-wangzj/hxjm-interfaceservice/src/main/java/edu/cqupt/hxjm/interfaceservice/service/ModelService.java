package edu.cqupt.hxjm.interfaceservice.service;
import com.alibaba.fastjson2.JSONObject;
import edu.cqupt.hxjm.interfaceservice.domain.ReID;
import lombok.Data;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Component
@Data
@Service
public class ModelService {
    @Autowired
    private RestTemplate restTemplate;
    @Value("${service-reid-img}")
    private String reidService_img;


    /**
     * 调用reid_url接口的方法
     * @param url 请求的URL
     * @param params 请求对象
     * @return 响应结果
     */
    public Object callReidService(String url, JSONObject params) {
        try {
            // 发送POST请求并接收响应
            Object response = restTemplate.postForObject(url, params, Object.class);
            return response;
        } catch (Exception e) {
            e.printStackTrace();
            return null;
        }
    }
}
