package edu.cqupt.hxjm.architecture;

import java.util.Arrays;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import edu.cqupt.hxjm.algdeployment.capability.api.CapabilityTaskController;
import edu.cqupt.hxjm.algdeployment.capability.service.CapabilityPlatform;
import edu.cqupt.hxjm.algdeployment.business.api.BusinessExceptionAdvice;

/** Verifies module assembly without starting Spring, databases or executor threads. */
public final class ModuleAssemblyCheck {
    public static void main(String[] args) throws Exception {
        String scanRoot = edu.cqupt.hxjm.RuoYiApplication.class.getPackage().getName();
        if (!CapabilityPlatform.class.getName().startsWith(scanRoot + ".")) {
            throw new AssertionError("Capability must remain inside the application component scan");
        }
        if (!Arrays.asList(CapabilityTaskController.class.getAnnotation(RequestMapping.class).value())
                .contains("/api/v1/business")) {
            throw new AssertionError("Public V1 paths changed");
        }
        if (!Arrays.asList(BusinessExceptionAdvice.class.getAnnotation(RestControllerAdvice.class).basePackages())
                .contains(CapabilityTaskController.class.getPackage().getName())) {
            throw new AssertionError("Capability must retain standard HTTP error handling");
        }
        for (String name : new String[] {"business.service.CapabilityPlatform", "service.impl.AiTaskRunServiceImpl"}) {
            try {
                Class.forName("edu.cqupt.hxjm.algdeployment." + name);
                throw new AssertionError("Retired class remains on classpath: " + name);
            } catch (ClassNotFoundException expected) { }
        }
        if (!Arrays.asList(edu.cqupt.hxjm.algdeployment.controller.FaceDatabaseController.class
                .getAnnotation(RequestMapping.class).value()).contains("/system/face_database")) {
            throw new AssertionError("Face business API path changed");
        }
        try {
            Class.forName("edu.cqupt.hxjm.system.controller.FaceDatabaseController");
            throw new AssertionError("Infrastructure still owns face business writes");
        } catch (ClassNotFoundException expected) { }
        System.out.println("ModuleAssemblyCheck passed: scan root, V1 paths, error handling, retired classes");
    }
}
