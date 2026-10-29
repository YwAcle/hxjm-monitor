## 共享视频与 BoT-SORT

默认通过当前前端端口使用共享服务：`/shared-media/live/camera_1/` 至
`camera_4/` 代理到本机 MediaMTX `18889`，`/ws/detections` 代理到共享分析服务
`28010`。开发者前端端口无需改变。服务端可用 `SHARED_MEDIA_ORIGIN` 和
`VIDEO_ANALYSIS_SHARED_ORIGIN` 覆盖这两个目标；旧启动器传入的本地分析地址
默认不影响共享服务选择。

默认显示独立的 WebRTC 实时视频，AI 断开或推理较慢不遮挡原视频。检测框为异步
结果，超过一秒或服务给出的有效期限就隐藏；独立接收链路的时间戳不保证严格对齐。
模型本身的预测、小目标恢复和交叉保护参数没有变化。界面可切换“同帧验收”，
此时 JPEG 与检测框成对显示，画面更新率受 AI 吞吐限制；仅该模式请求 JPEG。

显式设置 `VITE_VIDEO_ANALYSIS_MODE=local` 可以运行本目录的独立实验服务，
并恢复 `VITE_VIDEO_ANALYSIS_ORIGIN` 和 `VITE_MEDIA_PORT` 的原有含义。
代理保留 WHEP 会话的 `Location`，播放器关闭/重连时会通过代理发送 `DELETE`。

运行 `npm test` 和 `npm run build`。上述代理由 Vite 开发服务提供；发布静态构建
时，需要部署端为同源 `/shared-media`（包括 WHEP Location 与 DELETE）和
`/ws/detections` 配置相同的反向代理。

---

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Available Scripts11

In the project directory, you can run:

### `npm start`

Runs the app in the development mode.<br>
Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

The page will reload if you make edits.<br>
You will also see any lint errors in the console.

### `npm test`

Launches the test runner in the interactive watch mode.<br>
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `npm run build`

Builds the app for production to the `build` folder.<br>
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.<br>
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### `npm run eject`

**Note: this is a one-way operation. Once you `eject`, you can’t go back!**

If you aren’t satisfied with the build tool and configuration choices, you can `eject` at any time. This command will remove the single build dependency from your project.

Instead, it will copy all the configuration files and the transitive dependencies (Webpack, Babel, ESLint, etc) right into your project so you have full control over them. All of the commands except `eject` will still work, but they will point to the copied scripts so you can tweak them. At this point you’re on your own.

You don’t have to ever use `eject`. The curated feature set is suitable for small and middle deployments, and you shouldn’t feel obligated to use this feature. However we understand that this tool wouldn’t be useful if you couldn’t customize it when you are ready for it.

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).
