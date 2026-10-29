package edu.cqupt.hxjm.interfaceservice.controller;

import com.alibaba.fastjson2.JSONObject;
import edu.cqupt.hxjm.common.core.controller.BaseController;
import edu.cqupt.hxjm.common.core.domain.AjaxResult;
import edu.cqupt.hxjm.interfaceservice.service.ModelService;
import edu.cqupt.hxjm.interfaceservice.domain.ReID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;


@RestController
@RequestMapping("/interface-service")
public class InterfaceServiceController extends BaseController {
    @Autowired
    private ModelService modelService;
    @PostMapping("/reid")
    public AjaxResult ReIDSearch(@RequestBody ReID reID) {
        JSONObject params = new JSONObject();
        List <JSONObject> imgList = new ArrayList<>();
        Object resultObj = null;
        if(reID.getMethod() == 1){
            params.put("urlList",reID.getUrlList());
            reID.getImgList().forEach(item -> {
                JSONObject temp = new JSONObject();
                temp.put("name",item.getString("name"));
                temp.put("url",item.getString("url"));
                imgList.add(temp);
            });
            params.put("imgList",imgList);
            String reid_img_url = modelService.getReidService_img();
            resultObj = modelService.callReidService(reid_img_url, params);
        }else if(reID.getMethod() == 2){

        }
        return success(resultObj);
    }
}
