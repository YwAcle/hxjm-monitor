package edu.cqupt.hxjm.interfaceservice.controller;

import edu.cqupt.hxjm.interfaceservice.domain.StreamRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import javax.servlet.http.HttpServletResponse;
import java.io.*;

@RestController
@RequestMapping("/stream")
public class StreamProxyController {
    @PostMapping("/proxy")
    public ResponseEntity<Void> proxyStream(@RequestBody StreamRequest request, HttpServletResponse response) {
        String streamUrl = request.getStreamUrl();

        if (streamUrl == null || streamUrl.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }

        try {
            // 使用 FFmpeg 命令行工具处理视频流
            ProcessBuilder processBuilder = new ProcessBuilder(
                    "ffmpeg",
                    "-i", streamUrl,      // 输入流 URL
                    "-f", "flv",           // 输出 FLV 格式
                    "-c:v", "libx264",     // 使用 h264 编码
                    "-preset", "fast",     // 使用快速预设
                    "-tune", "zerolatency", // 调整为零延迟
                    "-f", "flv",           // 输出 FLV 格式
                    "pipe:1"               // 输出到标准输出流
            );

            // 启动 FFmpeg 进程
            Process process = processBuilder.start();
            InputStream ffmpegOutput = new BufferedInputStream(process.getInputStream());
            InputStream ffmpegError = new BufferedInputStream(process.getErrorStream()); // 错误流
            OutputStream responseOutput = response.getOutputStream();

            // 设置响应头
            response.setContentType("video/x-flv");
            response.setHeader("Cache-Control", "no-cache");
            response.setHeader("Connection", "keep-alive");
            response.setHeader("Transfer-Encoding", "chunked");  // 启用分块传输

            // 从 FFmpeg 输出流复制到 HTTP 响应输出流
            byte[] buffer = new byte[4096];
            int bytesRead;

            // 不断地读取 FFmpeg 输出流，并将数据实时写入 HTTP 响应流
            while ((bytesRead = ffmpegOutput.read(buffer)) != -1) {
                responseOutput.write(buffer, 0, bytesRead);
                responseOutput.flush();  // 确保数据实时发送到前端
            }

            // 处理错误流（如果有）
            BufferedReader errorReader = new BufferedReader(new InputStreamReader(ffmpegError));
            String line;
            while ((line = errorReader.readLine()) != null) {
                System.err.println(line);  // 打印错误信息到控制台
            }

            // 等待 FFmpeg 进程结束
            int exitCode = process.waitFor();
            if (exitCode != 0) {
                return ResponseEntity.status(500).build();
            }

            // 关闭流
            ffmpegOutput.close();
            ffmpegError.close();
            responseOutput.close();

            return ResponseEntity.ok().build();
        } catch (Exception e) {
            e.printStackTrace();
            return ResponseEntity.status(500).build();
        }
    }
}
