package edu.cqupt.hxjm.common.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
@ConfigurationProperties(prefix = "smartmonitor.ai")
public class AiTaskProperties {
    private String mtxBaseUrl;
    private String mtxHome;
    private String composeFile;
    private String publicHost;
    private Integer livePort;
    private String condaInit;
    private String condaEnv;
    private Map<String, TaskConfig> tasks;

    public static class TaskConfig {
        private String composeService;
        private String pythonDir;
        private String entry;

        public String getComposeService() {
            return composeService;
        }

        public void setComposeService(String composeService) {
            this.composeService = composeService;
        }

        public String getPythonDir() {
            return pythonDir;
        }

        public void setPythonDir(String pythonDir) {
            this.pythonDir = pythonDir;
        }

        public String getEntry() {
            return entry;
        }

        public void setEntry(String entry) {
            this.entry = entry;
        }
    }

    public String getMtxHome() {
        return mtxHome;
    }

    public String getMtxBaseUrl() {
        return mtxBaseUrl;
    }

    public void setMtxBaseUrl(String mtxBaseUrl) {
        this.mtxBaseUrl = mtxBaseUrl;
    }

    public void setMtxHome(String mtxHome) {
        this.mtxHome = mtxHome;
    }

    public String getComposeFile() {
        return composeFile;
    }

    public void setComposeFile(String composeFile) {
        this.composeFile = composeFile;
    }

    public String getPublicHost() {
        return publicHost;
    }

    public void setPublicHost(String publicHost) {
        this.publicHost = publicHost;
    }

    public Integer getLivePort() {
        return livePort;
    }

    public void setLivePort(Integer livePort) {
        this.livePort = livePort;
    }

    public String getCondaInit() {
        return condaInit;
    }

    public void setCondaInit(String condaInit) {
        this.condaInit = condaInit;
    }

    public String getCondaEnv() {
        return condaEnv;
    }

    public void setCondaEnv(String condaEnv) {
        this.condaEnv = condaEnv;
    }

    public Map<String, TaskConfig> getTasks() {
        return tasks;
    }

    public void setTasks(Map<String, TaskConfig> tasks) {
        this.tasks = tasks;
    }
}
