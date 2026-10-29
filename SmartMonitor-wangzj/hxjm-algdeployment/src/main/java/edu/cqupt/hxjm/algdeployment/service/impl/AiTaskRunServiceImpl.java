package edu.cqupt.hxjm.algdeployment.service.impl;

import edu.cqupt.hxjm.algdeployment.service.IAiTaskRunService;
import edu.cqupt.hxjm.common.config.AiTaskProperties;
import edu.cqupt.hxjm.common.constant.HttpStatus;
import edu.cqupt.hxjm.common.exception.ServiceException;
import edu.cqupt.hxjm.common.utils.StringUtils;
import org.springframework.stereotype.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.PostConstruct;
import javax.servlet.http.HttpServletRequest;
import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@Service
public class AiTaskRunServiceImpl implements IAiTaskRunService {
    private static final Logger log = LoggerFactory.getLogger(AiTaskRunServiceImpl.class);
    private final AiTaskProperties properties;
    private final Map<String, Process> pythonProcesses = new ConcurrentHashMap<>();
    private final Map<String, Boolean> pythonSupervisors = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newCachedThreadPool();

    public AiTaskRunServiceImpl(AiTaskProperties properties) {
        this.properties = properties;
    }

    @PostConstruct
    public void init() {
    }

    @Override
    public String startAndGetUrl(String task, int cameraId, HttpServletRequest request) {
        if (!task.matches("^[a-zA-Z0-9_-]+$")) {
            throw new ServiceException("task 格式不合法", HttpStatus.BAD_REQUEST);
        }
        Map<String, AiTaskProperties.TaskConfig> taskMap = properties.getTasks();
        if (taskMap == null || !taskMap.containsKey(task)) {
            throw new ServiceException("task 未配置或不支持", HttpStatus.NOT_FOUND);
        }
        AiTaskProperties.TaskConfig cfg = taskMap.get(task);

        boolean composeOk = runDockerCompose(task, cfg);
        if (!composeOk) {
            ensurePythonServer(cfg);
        }

        String host = StringUtils.isNotEmpty(properties.getPublicHost())
                ? properties.getPublicHost()
                : resolveHost(request);
        String scheme = resolveScheme(request);
        Integer port = properties.getLivePort();
        if (port == null || port <= 0) {
            throw new ServiceException("livePort 未配置或不合法", HttpStatus.ERROR);
        }
        return scheme + "://" + host + ":" + port + "/live/camera_" + cameraId + "_" + task;
    }

    private boolean runDockerCompose(String task, AiTaskProperties.TaskConfig cfg) {
        String composeFile = properties.getComposeFile();
        if (StringUtils.isEmpty(composeFile)) {
            throw new ServiceException("composeFile 未配置", HttpStatus.ERROR);
        }
        String service = StringUtils.isNotEmpty(cfg.getComposeService())
                ? cfg.getComposeService()
                : "ai-" + task;

        List<String> cmd = new ArrayList<>();
        cmd.add("docker");
        cmd.add("compose");
        cmd.add("-f");
        cmd.add(composeFile);
        cmd.add("up");
        cmd.add(service);
        cmd.add("-d");

        int code = execAndCheck(cmd, null);
        return code == 0;
    }

    private void ensurePythonServer(AiTaskProperties.TaskConfig cfg) {
        String key = cfg.getPythonDir();
        if (Boolean.TRUE.equals(pythonSupervisors.get(key))) {
            return;
        }

        String base = properties.getMtxHome();
        if (StringUtils.isEmpty(base)) {
            throw new ServiceException("mtxHome 未配置", HttpStatus.ERROR);
        }
        File workDir = new File(base, cfg.getPythonDir());
        if (!workDir.exists() || !workDir.isDirectory()) {
            throw new ServiceException("pythonDir 不存在: " + workDir.getAbsolutePath(), HttpStatus.ERROR);
        }
        String entry = cfg.getEntry();
        if (StringUtils.isEmpty(entry)) {
            throw new ServiceException("entry 未配置", HttpStatus.ERROR);
        }
        pythonSupervisors.put(key, true);
        executor.submit(() -> {
            while (Boolean.TRUE.equals(pythonSupervisors.get(key))) {
                Process p = startPythonProcess(cfg, workDir, entry);
                try {
                    int code = p.waitFor();
                    log.warn("python 进程退出 key={} code={}", key, code);
                    Thread.sleep(2000);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        });
    }

    private Process startPythonProcess(AiTaskProperties.TaskConfig cfg, File workDir, String entry) {
        String key = cfg.getPythonDir();
        String condaInit = properties.getCondaInit();
        String condaEnv = properties.getCondaEnv();
        boolean useConda = StringUtils.isNotEmpty(condaInit) && new File(condaInit).exists() && StringUtils.isNotEmpty(condaEnv);

        List<String> cmd = new ArrayList<>();
        if (useConda) {
            String script = "source " + condaInit + " && conda activate " + condaEnv + " && python " + entry;
            cmd.add("bash");
            cmd.add("-lc");
            cmd.add(script);
        } else {
            cmd.add("python");
            cmd.add(entry);
        }
        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.directory(workDir);
        pb.redirectErrorStream(true);
        try {
            Process p = pb.start();
            pythonProcesses.put(key, p);
            attachLogReader(key, p);
            return p;
        } catch (IOException e) {
            throw new ServiceException("python 启动失败", HttpStatus.ERROR).setDetailMessage(e.getMessage());
        }
    }

    private void attachLogReader(String key, Process p) {
        InputStream is = p.getInputStream();
        executor.submit(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    log.info("python[{}] {}", key, line);
                }
            } catch (IOException ioe) {
                log.warn("python 日志读取异常 key={} msg={}", key, ioe.getMessage());
            }
        });
    }

    private boolean isPortListening(String host, int port) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 800);
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    private int execAndCheck(List<String> cmd, File dir) {
        ProcessBuilder pb = new ProcessBuilder(cmd);
        if (dir != null) {
            pb.directory(dir);
        }
        pb.redirectErrorStream(true);
        try {
            Process p = pb.start();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                while (reader.readLine() != null) {
                }
            }
            return p.waitFor();
        } catch (IOException | InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ServiceException("命令执行异常", HttpStatus.ERROR).setDetailMessage(e.getMessage());
        }
    }

    private String resolveHost(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-Host");
        if (StringUtils.isNotEmpty(forwarded)) {
            return forwarded.split(",")[0].trim();
        }
        String host = request.getHeader("Host");
        if (StringUtils.isNotEmpty(host)) {
            if (host.contains(":")) {
                return host.substring(0, host.indexOf(':'));
            }
            return host;
        }
        return "localhost";
    }

    private String resolveScheme(HttpServletRequest request) {
        String proto = request.getHeader("X-Forwarded-Proto");
        if (StringUtils.isNotEmpty(proto)) {
            return proto;
        }
        String scheme = request.getScheme();
        return StringUtils.isNotEmpty(scheme) ? scheme : "http";
    }

    private String serviceSuffixFallback(AiTaskProperties.TaskConfig cfg) {
        String s = cfg.getComposeService();
        if (StringUtils.isNotEmpty(s)) {
            return s;
        }
        return "";
    }
}
