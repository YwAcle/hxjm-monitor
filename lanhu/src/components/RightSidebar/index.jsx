import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { ChevronDown, ChevronUp, Download, Eraser } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './RightSidebar.module.css';
import { useLLMReportWebSocket } from '../../contexts/LLMReportWebSocketContext';
import VideoModal from '../VideoModal/VideoModal';
import { businessApi } from '../../services/businessApi';
import { resolveReportPlayback } from '../../services/reportPlayback';
import PedestrianSearchResult from './PedestrianSearchResult';
import AgentBusinessResults from './AgentBusinessResults';
import { collectAgentResults } from '../../services/agentResults';
import { getPedestrianSearchResult, getPendingPedestrianSelection } from '../../services/pedestrianSearch';
import {
  clearAgentMemory,
  createSessionId,
  isValidSessionId,
  MAX_IMAGE_SIZE,
  SUPPORTED_IMAGE_TYPES,
  sendAgentImageMessage,
  sendAgentMessage,
  streamAgentMessage,
} from '../../services/agentChat';

// 导入图片资源
import lineDeco from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_top_mid.png';
import titleBarBg from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bg_mid.png';
import titleIcon from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_arrow.png';
import cornerDeco from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_large.png';
import centerDeco from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/right_small_header_bottom.png';
import aiAvatar from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPngbad65e8be9e7f404648cc03005a9eee86ccfe3bb1ab3a569856b8f9636196c0f.png';
import userAvatar from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPngb6d44331bb45449c8546fdf36e6ea19f8712368c3e2449dff0658fd33acc6e79.png';
import cameraIcon from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPnge8fa8a0b5bde953f6cf595581b38e20e2cdcb2afc8e6e3b2eb2048c703b7efc7.png';
import micIcon from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPng4a04466ab02f8a1707c95728107ce5bf60392d574ce8234effc469039fd102b6.png';
import sendIcon from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/send_button.png';
import sectionIcon from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPng5843f3d441a0930360c3f0476f0873ac3ead7b26f3bf0e4813d5038ced68aa82.png';

// 获取浏览器的语音识别 API
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const WELCOME_MESSAGE = '欢迎使用火眼金睛大模型，我可以帮您查找人员、分析监控数据。请输入指令或上传图片开始使用。';

const createWelcomeMessage = () => ({
  id: Date.now(),
  type: 'ai',
  content: WELCOME_MESSAGE,
});

const downloadImage = (imageDataUrl) => {
  if (typeof imageDataUrl !== 'string' || !imageDataUrl) return;

  const link = document.createElement('a');
  link.href = imageDataUrl;
  link.download = `super-resolution-${Date.now()}.jpg`;
  document.body.appendChild(link);
  link.click();
  link.remove();
};

const getSuperResolutionStatusMessage = (data) => {
  if (data?.status === 'missing_image') {
    return data.text || '请上传需要超分的图片。';
  }
  if (data?.status === 'invalid_image') {
    return data.text || '图片解码失败，请重新选择图片。';
  }
  return data?.text || data?.summary || '请求已处理完成。';
};

// 检测是否是"找人"相关指令
const isPersonSearchCommand = (text) => {
  const keywords = ['找人', '查找', '搜索', '寻找', '查人', '找这个人', '帮我找', '识别', '是谁', '查一下'];
  return keywords.some(keyword => text.includes(keyword));
};

// 日志报告组件 - 使用 WebSocket 实时数据
function LogReport() {
  const { reports, isConnected } = useLLMReportWebSocket();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [playbackNotice, setPlaybackNotice] = useState(null);
  
  // 视频播放弹窗状态
  const [videoModal, setVideoModal] = useState({
    visible: false,
    url: '',
    title: '',
    time: ''
  });
  
  // 显示最新的 20 条报告（按时间倒序）
  const displayReports = useMemo(() => {
    return reports
      .slice()
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .slice(0, 20);
  }, [reports]);

  // 根据 prompt_type 获取类型配置
  const getTypeConfig = (promptType) => {
    if (promptType === 'vad') {
      return { color: '#41B1FF', label: 'VAD' };
    } else if (promptType === 'reid') {
      return { color: '#00D4FF', label: 'ReID' };
    }
    return { color: '#41B1FF', label: '分析' };
  };

  // 格式化时间
  const formatTime = (timeStr) => {
    if (!timeStr) return '';
    try {
      const date = new Date(timeStr);
      return date.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit',
        hour12: false 
      });
    } catch {
      return timeStr;
    }
  };

  // 获取事件类型配置（打架等危险事件用黄色高亮）
  const getEventTypeConfig = (eventType) => {
    const dangerEvents = ['violence', 'fight', 'fire', 'fall'];
    const isDanger = dangerEvents.includes(eventType);
    
    const typeMap = {
      'violence': '暴力行为',
      'non-violence': '正常行为',
      'fall': '摔倒检测',
      'fire': '火灾检测',
      'fight': '打架检测',
      'stranger': '陌生人'
    };
    
    return {
      name: typeMap[eventType] || eventType || '行为分析',
      isHighlight: isDanger
    };
  };

  // 处理图片URL
  const getThumbnailUrl = (report) => {
    // 如果有缩略图字段
    if (report.thumbnail) {
      if (report.thumbnail.startsWith('data:image')) {
        return report.thumbnail.replace(';base64:', ';base64,');
      }
      if (!report.thumbnail.startsWith('http') && !report.thumbnail.startsWith('/')) {
        return `data:image/jpeg;base64,${report.thumbnail}`;
      }
      return report.thumbnail;
    }
    // 返回默认占位图
    return null;
  };

  // 点击缩略图播放视频
  const handleThumbnailClick = async (report) => {
    setPlaybackNotice({ id: report.id, text: '正在查找录像…' });
    try {
      const media = await resolveReportPlayback(report, businessApi);
      setVideoModal({
        visible: true,
        ...media,
        title: getEventTypeConfig(report.report_json?.event_type).name,
        time: formatTime(report.created_at)
      });
      setPlaybackNotice(null);
    } catch (error) {
      setPlaybackNotice({ id: report.id, text: error.message });
    }
  };

  // 关闭视频弹窗
  const closeVideoModal = () => {
    setVideoModal({ visible: false, url: '', title: '', time: '' });
  };

  return (
    <>
      <div className={`${styles.reportPanel} ${isCollapsed ? styles.reportPanelCollapsed : ''}`}>
        {/* 报告标题 */}
        <div className={styles.reportHeader}>
          <span className={styles.reportTitle}>大模型监控报告</span>
          <button
            type="button"
            className={styles.reportCollapseButton}
            onClick={() => setIsCollapsed(previous => !previous)}
            aria-label={isCollapsed ? '展开大模型监控报告' : '折叠大模型监控报告'}
            aria-expanded={!isCollapsed}
            title={isCollapsed ? '展开报告' : '折叠报告'}
          >
            {isCollapsed ? <ChevronDown aria-hidden="true" /> : <ChevronUp aria-hidden="true" />}
          </button>
          <span className={styles.reportStatus}>
            {isConnected ? '● 实时' : '○ 离线'}
          </span>
        </div>
        {!isCollapsed && (
          <>
            <div
              className={`${styles.centerDeco} flex-row`}
              style={{ backgroundImage: `url(${centerDeco})` }}
            />

            {/* 报告内容区域 */}
            <div className={styles.reportBody}>
              {/* 日志列表 */}
              <div className={styles.logListContainer}>
              {displayReports.length > 0 ? (
                displayReports.map((report) => {
                  const typeConfig = getTypeConfig(report.prompt_type);
                  const eventConfig = getEventTypeConfig(report.report_json?.event_type);
                  const confidence = report.report_json?.confidence;
                  const thumbnailUrl = getThumbnailUrl(report);
                  const hasVideo = !!(report.episode_id || report.report_json?.route?.length || report.record_url);

                  return (
                    <div key={report.id} className={styles.logCard}>
                      {/* 左侧缩略图 */}
                      <div
                        className={`${styles.logThumbnail} ${hasVideo ? styles.clickable : ''}`}
                        onClick={() => hasVideo && handleThumbnailClick(report)}
                        title={hasVideo ? '点击播放视频' : '无可用录像'}
                        aria-disabled={!hasVideo}
                      >
                        {thumbnailUrl ? (
                          <img src={thumbnailUrl} alt="缩略图" />
                        ) : (
                          <div className={styles.logThumbnailPlaceholder}>
                            <span>📹</span>
                          </div>
                        )}
                        {hasVideo && (
                          <div className={styles.playIcon}>▶</div>
                        )}
                      </div>

                      {/* 右侧内容 */}
                      <div className={styles.logCardContent}>
                        {/* 卡片头部 */}
                        <div className={styles.logCardHeader}>
                          <span className={styles.logTime}>{formatTime(report.created_at)}</span>
                          <div className={styles.logTags}>
                            <span
                              className={styles.logTag}
                              style={{ backgroundColor: `${typeConfig.color}20`, color: typeConfig.color }}
                            >
                              {typeConfig.label}
                            </span>
                            <span
                              className={`${styles.logEventTag} ${eventConfig.isHighlight ? styles.highlight : ''}`}
                            >
                              {eventConfig.name}
                            </span>
                            {!hasVideo && (
                              <span className={styles.unavailableVideo}>无可用录像</span>
                            )}
                          </div>
                        </div>

                        {/* 报告内容 */}
                        <div className={styles.logCardBody}>
                          <p className={styles.logText}>
                            {report.report_json?.summary || report.report_text?.substring(0, 80) || '暂无描述'}
                          </p>
                          {playbackNotice?.id === report.id && <p role="status">{playbackNotice.text}</p>}

                          {/* 置信度显示 - 统一绿色 */}
                          {confidence !== undefined && (
                            <div className={styles.logConfidence}>
                              <span className={styles.confidenceLabel}>置信度</span>
                              <div className={styles.confidenceBar}>
                                <div
                                  className={styles.confidenceFill}
                                  style={{ width: `${confidence * 100}%` }}
                                />
                              </div>
                              <span className={styles.confidenceValue}>{(confidence * 100).toFixed(0)}%</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className={styles.logEmpty}>
                  {isConnected ? '暂无分析报告' : '正在连接...'}
                </div>
              )}
              </div>
            </div>
          </>
        )}
      </div>
      
      {/* 视频播放弹窗 */}
      <VideoModal
        visible={videoModal.visible}
        url={videoModal.url}
        playback={videoModal.playback}
        title={videoModal.title}
        time={videoModal.time}
        onClose={closeVideoModal}
      />
    </>
  );
}

// 公共报告内容组件 - 包含出现频率、总结、关键帧缩略图
function ReportContent({ 
  frequencyData = [], 
  summary = '暂无总结', 
  thumbnails = [], 
  onThumbnailClick
}) {
  // 限制缩略图最多显示20个
  const MAX_THUMBNAILS = 20;
  const displayThumbnails = thumbnails.slice(0, MAX_THUMBNAILS);
  const hasMoreThumbnails = thumbnails.length > MAX_THUMBNAILS;
  
  // 缩略图滚动容器引用
  const thumbnailsScrollRef = useRef(null);
  
  // 处理滚轮事件（下滑时从左往右滚动）- 使用非被动监听器
  useEffect(() => {
    const scrollContainer = thumbnailsScrollRef.current;
    if (scrollContainer && displayThumbnails.length > 3) {
      const handleWheel = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const delta = e.deltaY > 0 ? 50 : -50; // 下滑向右，上滑向左
        scrollContainer.scrollLeft += delta;
      };
      
      // 使用非被动监听器，允许 preventDefault
      scrollContainer.addEventListener('wheel', handleWheel, { passive: false });
      
      return () => {
        scrollContainer.removeEventListener('wheel', handleWheel);
      };
    }
  }, [displayThumbnails.length]);
  
  // 计算 y 轴最大值（向上取整到最近的偶数）
  const validFrequencyData = frequencyData && frequencyData.length > 0 ? frequencyData : [];
  const maxValue = validFrequencyData.length > 0 
    ? Math.max(...validFrequencyData.map(d => d.value || 0), 0) 
    : 0;
  const yAxisMax = maxValue === 0 ? 10 : Math.ceil(maxValue / 2) * 2;
  const yAxisInterval = yAxisMax <= 10 ? 2 : Math.ceil(yAxisMax / 5);
  
  // ECharts 配置
  const getChartOption = () => ({
    grid: {
      left: 5,
      right: 5,
      top: 10,
      bottom: 5,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: validFrequencyData.map(d => d.label || ''),
      axisLine: {
        lineStyle: {
          color: 'rgba(255, 255, 255, 0.2)'
        }
      },
      axisTick: {
        show: false
      },
      axisLabel: {
        color: 'rgba(255, 255, 255, 0.7)',
        fontSize: 14,
        lineHeight: 20,
        textAlign: 'right',
        fontStyle: 'normal',
        fontFamily: 'PingFangSC, PingFang SC',
        fontWeight: 400,
        interval: 0,
        rotate: 0
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: yAxisMax,
      interval: yAxisInterval,
      axisLine: {
        show: false
      },
      axisTick: {
        show: false
      },
      axisLabel: {
        color: 'rgba(255, 255, 255, 0.7)',
        fontSize: 16,
        fontFamily: 'PingFangSC, PingFang SC',
        fontWeight: 400,
        lineHeight: 24,
        textAlign: 'right',
        fontStyle: 'normal',
      },
      splitLine: {
        lineStyle: {
          color: 'rgba(255, 255, 255, 0.15)'
        }
      }
    },
    series: [{
      type: 'bar',
      data: validFrequencyData.map(d => d.value || 0),
      barWidth: 20,
      itemStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: '#7DD8FF' },
            { offset: 0.5, color: '#41B1FF' },
            { offset: 1, color: '#2A7AB8' }
          ]
        },
        borderRadius: [3, 3, 0, 0]
      }
    }]
  });
  
  return (
    <>
          {/* 内容区域 - 左右布局 */}
          <div className={styles.reportContent}>
          {/* 左侧 - 出现频率柱状图 */}
          <div className={styles.frequencySection}>
            <div className={styles.sectionHeader}>
              <div 
                className={styles.sectionIcon}
                style={{ backgroundImage: `url(${sectionIcon})` }}
              />
              <span className={styles.sectionTitle}>出现频率</span>
            </div>
            
            {/* ECharts 柱状图 */}
            <ReactECharts 
              option={getChartOption()} 
              style={{ height: '200px', width: '270px' }}
              opts={{ renderer: 'canvas' }}
            />
          </div>
          
          {/* 右侧 - 文本总结 */}
          <div className={styles.summarySection}>
            <div className={styles.sectionHeader}>
              <div 
                className={styles.sectionIcon}
                style={{ backgroundImage: `url(${sectionIcon})` }}
              />
              <span className={styles.sectionTitle}>文本总结</span>
            </div>
            <p className={styles.summaryText}>{summary}</p>
          </div>
        </div>
        
        {/* 关键帧缩略图 */}
        <div className={styles.thumbnailsSection}>
          <div className={styles.sectionHeader}>
            <div 
              className={styles.sectionIcon}
              style={{ backgroundImage: `url(${sectionIcon})` }}
            />
            <span className={styles.sectionTitle}>关键帧缩略图</span>
          {hasMoreThumbnails && (
            <span className={styles.thumbnailCount}>(显示前{MAX_THUMBNAILS}个，共{thumbnails.length}个)</span>
          )}
          </div>
          
        <div 
          ref={thumbnailsScrollRef}
          className={styles.thumbnailsGrid}
        >
          {displayThumbnails && displayThumbnails.length > 0 ? (
            displayThumbnails.map((thumb, index) => {
                const hasVideo = !!thumb.recording;
                
                return (
                  <div key={index} className={styles.thumbnailItem}>
                    <div
                      className={`${styles.thumbnailImageWrapper} ${hasVideo ? styles.clickable : ''}`}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                      if (hasVideo && onThumbnailClick) {
                        onThumbnailClick(thumb);
                        }
                      }}
                      title={hasVideo ? '点击播放视频' : ''}
                    >
                      <img 
                        src={thumb.image} 
                        alt={thumb.label} 
                        className={styles.thumbnailImage}
                        onError={(e) => {
                          console.error('[LLM_CHAT] ❌ 图片加载失败:', {
                            index,
                            label: thumb.label,
                          imageUrl: thumb.image?.substring(0, 100)
                          });
                          e.target.style.display = 'none';
                        }}
                        onLoad={() => {
                          console.log('[LLM_CHAT] ✅ 图片加载成功:', thumb.label);
                        }}
                      />
                      {hasVideo && (
                        <div className={styles.playIcon}>▶</div>
                      )}
                    </div>
                    <span className={styles.thumbnailLabel}>{thumb.label}</span>
                  </div>
                );
              })
            ) : (
              <div className={styles.thumbnailItem}>
                <div style={{ 
                  width: '173px', 
                  height: '130px', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  background: 'rgba(255, 255, 255, 0.05)',
                  borderRadius: '4px',
                  border: '1px solid rgba(65, 177, 255, 0.3)',
                  color: 'rgba(255, 255, 255, 0.5)'
                }}>
                  暂无关键帧
                </div>
              </div>
            )}
          </div>
        </div>
    </>
  );
}

// 异常报告组件 - 显示 type=vad 的异常数据
function AnomalyReport({ data }) {
  if (!data) return null;
  
  const { 
    date = '',  // 日期，格式：2026年01月05日
    frequencyData = [],  // 出现频率数据
    summary = '暂无总结',  // 文本总结
    thumbnails = []  // 关键帧缩略图
  } = data;
  
  // 视频播放弹窗状态
  const [videoModal, setVideoModal] = useState({
    visible: false,
    url: '',
    title: '',
    time: ''
  });
  
  // 点击缩略图播放视频
  const handleThumbnailClick = (thumb) => {
    if (thumb.recording) {
      setVideoModal({
        visible: true,
        url: thumb.recording,
        title: '异常监控报告',
        time: thumb.label
      });
    }
  };
  
  // 关闭视频弹窗
  const closeVideoModal = () => {
    setVideoModal({ visible: false, url: '', title: '', time: '' });
  };
  
  // 格式化日期显示
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    // 如果后端返回的是标准格式，直接使用
    // 如果返回的是日期字符串，需要格式化
    if (dateStr.includes('年') && dateStr.includes('月') && dateStr.includes('日')) {
      return dateStr;
    }
    // 尝试解析日期字符串
    try {
      const date = new Date(dateStr);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      return `${year}年${month}月${day}日`;
    } catch {
      return dateStr;
    }
  };
  
  return (
    <>
      <div className={styles.reportPanel}>
        {/* 报告标题 */}
        <div className={styles.reportHeader}>
          <span className={styles.reportTitle}>异常监控报告：{formatDate(date)}</span>
        </div>
        <div 
          className={`${styles.centerDeco} flex-row`}
          style={{ backgroundImage: `url(${centerDeco})` }}
        />
        
        {/* 报告内容区域 */}
        <div className={styles.reportBody}>
          <ReportContent
            frequencyData={frequencyData}
            summary={summary}
            thumbnails={thumbnails}
            onThumbnailClick={handleThumbnailClick}
          />
        </div>
      </div>
      
      {/* 视频播放弹窗 */}
      <VideoModal
        visible={videoModal.visible}
        url={videoModal.url}
        title={videoModal.title}
        time={videoModal.time}
        onClose={closeVideoModal}
      />
    </>
  );
}

// 人员查找报告组件
function PersonSearchReport({ data }) {
  if (!data) return null;
  
  const { name = '未知人员', frequencyData = [], summary = '暂无总结', thumbnails = [] } = data;
  
  // 视频播放弹窗状态
  const [videoModal, setVideoModal] = useState({
    visible: false,
    url: '',
    title: '',
    time: ''
  });
  
  // 点击缩略图播放视频
  const handleThumbnailClick = (thumb) => {
    console.log('[LLM_CHAT] 🖱️ 缩略图被点击:', {
      label: thumb.label,
      recording: thumb.recording,
      hasRecording: !!thumb.recording
    });
    
    if (thumb.recording) {
      console.log('[LLM_CHAT] ▶️ 打开视频弹窗:', thumb.recording);
      setVideoModal({
        visible: true,
        url: thumb.recording,
        title: `人员查找 - ${name}`,
        time: thumb.label
      });
    } else {
      console.warn('[LLM_CHAT] ⚠️ 缩略图没有 recording 字段');
    }
  };
  
  // 关闭视频弹窗
  const closeVideoModal = () => {
    setVideoModal({ visible: false, url: '', title: '', time: '' });
  };
  
  return (
    <>
      <div className={styles.reportPanel}>
        {/* 报告标题 */}
        <div className={styles.reportHeader}>
          <span className={styles.reportTitle}>人员查找报告：{name}</span>
        </div>
        <div 
          className={`${styles.centerDeco} flex-row`}
          style={{ backgroundImage: `url(${centerDeco})` }}
        />
        
        {/* 报告内容区域 */}
        <div className={styles.reportBody}>
          <ReportContent
            frequencyData={frequencyData}
            summary={summary}
            thumbnails={thumbnails}
            onThumbnailClick={handleThumbnailClick}
          />
        </div>
      </div>
      
      {/* 视频播放弹窗 */}
      <VideoModal
        visible={videoModal.visible}
        url={videoModal.url}
        title={videoModal.title}
        time={videoModal.time}
        onClose={closeVideoModal}
      />
    </>
  );
}

function RightSidebar() {
  // 对话列表状态
  const [conversations, setConversations] = useState([]);
  // 当前对话ID
  const [currentConversationId, setCurrentConversationId] = useState(null);
  // 消息列表状态（当前对话的消息）
  const [messages, setMessages] = useState([createWelcomeMessage()]);
  const [isSending, setIsSending] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const chatAbortControllerRef = useRef(null);
  
  // 当前显示的报告组件
  // 类型: 'personSearch' | 'log' | 'anomaly'
  const [currentReport, setCurrentReport] = useState('log');
  
  // ReID 报告数据状态
  const [reidReportData, setReidReportData] = useState(null);
  
  // 异常报告数据状态
  const [anomalyReportData, setAnomalyReportData] = useState(null);
  
  // 自动切换定时器引用
  const autoSwitchTimerRef = useRef(null);
  
  // 输入内容状态
  const [inputText, setInputText] = useState('');
  
  // 上传图片同时保留 File（用于 FormData）和 data URL（用于预览）。
  const [uploadedImage, setUploadedImage] = useState(null);
  
  // 文件输入引用
  const fileInputRef = useRef(null);
  
  // 消息列表引用（用于自动滚动）
  const messagesEndRef = useRef(null);
  
  // 对话下拉菜单延迟隐藏定时器
  const conversationDropdownTimerRef = useRef(null);
  // 下拉菜单显示状态
  const [showDropdown, setShowDropdown] = useState(false);
  
  // 会话标题编辑状态
  const [editingTitleId, setEditingTitleId] = useState(null);
  const [editingTitleValue, setEditingTitleValue] = useState('');
  const titleInputRef = useRef(null);
  
  // 清理定时器
  useEffect(() => {
    return () => {
      chatAbortControllerRef.current?.abort();
      if (conversationDropdownTimerRef.current) {
        clearTimeout(conversationDropdownTimerRef.current);
      }
    };
  }, []);
  
  // localStorage 键名
  const STORAGE_KEY = 'llm_conversations';
  const CURRENT_CONVERSATION_KEY = 'llm_current_conversation_id';
  
  // 从 localStorage 加载对话数据
  useEffect(() => {
    try {
      const savedConversations = localStorage.getItem(STORAGE_KEY);
      const savedCurrentId = localStorage.getItem(CURRENT_CONVERSATION_KEY);
      
      if (savedConversations) {
        const storedConversations = JSON.parse(savedConversations);
        if (!Array.isArray(storedConversations) || storedConversations.length === 0) {
          throw new Error('本地会话数据格式不正确');
        }

        // 兼容旧版数据：旧会话没有 sessionId 时复用合法 id，否则生成新 UUID。
        const parsed = storedConversations.map(conversation => ({
          ...conversation,
          sessionId: isValidSessionId(conversation.sessionId)
            ? conversation.sessionId
            : (isValidSessionId(conversation.id) ? conversation.id : createSessionId()),
          messages: Array.isArray(conversation.messages) && conversation.messages.length > 0
            ? conversation.messages
            : [createWelcomeMessage()],
        }));
        setConversations(parsed);
        
        // 如果有保存的当前对话ID，且该对话存在，则恢复
        if (savedCurrentId && parsed.find(c => c.id === savedCurrentId)) {
          setCurrentConversationId(savedCurrentId);
          const currentConv = parsed.find(c => c.id === savedCurrentId);
          if (currentConv && currentConv.messages) {
            setMessages(currentConv.messages);
          }
        } else if (parsed.length > 0) {
          // 否则使用第一个对话
          const firstConv = parsed[0];
          setCurrentConversationId(firstConv.id);
          setMessages(firstConv.messages || []);
        }
        saveConversationsToStorage(
          parsed,
          savedCurrentId && parsed.some(c => c.id === savedCurrentId)
            ? savedCurrentId
            : parsed[0].id,
        );
      } else {
        // 如果没有保存的对话，创建默认对话
        const defaultId = createSessionId();
        const defaultConv = {
          id: defaultId,
          sessionId: defaultId,
          title: '新对话 1',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messages: [createWelcomeMessage()]
        };
        setConversations([defaultConv]);
        setCurrentConversationId(defaultId);
        setMessages(defaultConv.messages);
        saveConversationsToStorage([defaultConv], defaultId);
      }
    } catch (error) {
      console.error('[LLM_CHAT] ❌ 加载对话数据失败:', error);
      const fallbackId = createSessionId();
      const fallbackConversation = {
        id: fallbackId,
        sessionId: fallbackId,
        title: '新对话 1',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [createWelcomeMessage()],
      };
      setConversations([fallbackConversation]);
      setCurrentConversationId(fallbackId);
      setMessages(fallbackConversation.messages);
      saveConversationsToStorage([fallbackConversation], fallbackId);
    }
  }, []);
  
  // 保存对话到 localStorage
  const saveConversationsToStorage = (convs, currentId) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(convs));
      if (currentId) {
        localStorage.setItem(CURRENT_CONVERSATION_KEY, currentId);
      }
    } catch (error) {
      console.error('[LLM_CHAT] ❌ 保存对话数据失败:', error);
    }
  };
  
  // 更新会话标题
  const updateConversationTitle = useCallback((conversationId, newTitle) => {
    if (!newTitle || !newTitle.trim()) {
      return;
    }
    
    setConversations(prevConvs => {
      const updatedConversations = prevConvs.map(conv => {
        if (conv.id === conversationId) {
          return {
            ...conv,
            title: newTitle.trim(),
            updatedAt: new Date().toISOString()
          };
        }
        return conv;
      });
      
      saveConversationsToStorage(updatedConversations, currentConversationId);
      return updatedConversations;
    });
  }, [currentConversationId]);
  
  // 处理双击编辑标题
  const handleTitleDoubleClick = useCallback((conversationId) => {
    const conv = conversations.find(c => c.id === conversationId);
    if (conv) {
      setEditingTitleId(conversationId);
      setEditingTitleValue(conv.title);
      // 聚焦到输入框
      setTimeout(() => {
        titleInputRef.current?.focus();
        titleInputRef.current?.select();
      }, 0);
    }
  }, [conversations]);
  
  // 保存标题编辑
  const handleTitleSave = useCallback(() => {
    if (editingTitleId && editingTitleValue.trim()) {
      updateConversationTitle(editingTitleId, editingTitleValue.trim());
    }
    setEditingTitleId(null);
    setEditingTitleValue('');
  }, [editingTitleId, editingTitleValue, updateConversationTitle]);
  
  // 取消标题编辑
  const handleTitleCancel = useCallback(() => {
    setEditingTitleId(null);
    setEditingTitleValue('');
  }, []);
  
  // 标题输入框键盘事件
  const handleTitleKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleTitleSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleTitleCancel();
    }
  }, [handleTitleSave, handleTitleCancel]);
  
  // 点击外部取消编辑
  useEffect(() => {
    if (!editingTitleId) return;
    
    const handleClickOutside = (e) => {
      if (titleInputRef.current && !titleInputRef.current.contains(e.target)) {
        handleTitleSave();
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [editingTitleId, handleTitleSave]);

  // 当消息变化时，更新当前对话并保存到 localStorage
  useEffect(() => {
    if (conversations.length > 0 && currentConversationId && messages.length > 0) {
      // 更新当前对话的消息
      setConversations(prevConvs => {
        const updatedConversations = prevConvs.map(conv => {
          if (conv.id === currentConversationId) {
            // 自动生成标题（使用第一条用户消息的前20个字符）
            // 只有标题是"新对话"（没有编号）或"新对话 X"格式时，才自动更新
            const firstUserMessage = messages.find(m => m.type === 'user' && m.content);
            const isNewConversationPattern = /^新对话( \d+)?$/.test(conv.title);
            
            let newTitle = conv.title;
            if (isNewConversationPattern && firstUserMessage) {
              // 提取用户消息的文本内容（去除可能的图片等）
              const messageText = typeof firstUserMessage.content === 'string' 
                ? firstUserMessage.content 
                : firstUserMessage.content?.text || '';
              
              if (messageText.trim()) {
                newTitle = messageText.trim().substring(0, 20);
                if (messageText.length > 20) {
                  newTitle += '...';
                }
              }
            }
            
            return {
              ...conv,
              messages: messages,
              updatedAt: new Date().toISOString(),
              title: newTitle
            };
          }
          return conv;
        });
        
        // 保存到 localStorage
        saveConversationsToStorage(updatedConversations, currentConversationId);
        return updatedConversations;
      });
    }
  }, [messages, currentConversationId]);
  
  // 添加新对话
  const handleAddConversation = () => {
    if (isSending || isClearing) return;

    // 计算新对话的编号（统计所有"新对话"开头的对话）
    const newConversationCount = conversations.filter(c => c.title.startsWith('新对话')).length + 1;
    const newTitle = `新对话 ${newConversationCount}`;
    
    const newId = createSessionId();
    const newConversation = {
      id: newId,
      sessionId: newId,
      title: newTitle,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [createWelcomeMessage()]
    };
    
    const updatedConversations = [...conversations, newConversation];
    setConversations(updatedConversations);
    setCurrentConversationId(newId);
    setMessages(newConversation.messages);
    setCurrentReport('log');
    setReidReportData(null);
    setAnomalyReportData(null);
    setInputText('');
    setUploadedImage(null);
    saveConversationsToStorage(updatedConversations, newId);
    
    console.log('[LLM_CHAT] ✅ 创建新对话:', newId);
  };
  
  // 删除对话
  const handleDeleteConversation = (conversationId) => {
    if (isSending || isClearing) return;

    if (conversations.length <= 1) {
      alert('至少需要保留一个对话');
      return;
    }

    const conversationToDelete = conversations.find(c => c.id === conversationId);
    const updatedConversations = conversations.filter(c => c.id !== conversationId);
    setConversations(updatedConversations);
    
    // 如果删除的是当前对话，切换到第一个对话
    if (conversationId === currentConversationId) {
      const firstConv = updatedConversations[0];
      setCurrentConversationId(firstConv.id);
      setMessages(firstConv.messages || []);
      setCurrentReport('log');
      setReidReportData(null);
      setAnomalyReportData(null);
      saveConversationsToStorage(updatedConversations, firstConv.id);
    } else {
      saveConversationsToStorage(updatedConversations, currentConversationId);
    }

    if (conversationToDelete?.sessionId) {
      clearAgentMemory(conversationToDelete.sessionId).catch(error => {
        console.warn('[LLM_CHAT] 删除本地对话后清理后端记忆失败:', error.message);
      });
    }
    
    console.log('[LLM_CHAT] 🗑️ 删除对话:', conversationId);
  };
  
  // 切换对话
  const handleSwitchConversation = (conversationId) => {
    if (isSending || isClearing) return;

    const targetConv = conversations.find(c => c.id === conversationId);
    if (targetConv) {
      setCurrentConversationId(conversationId);
      setMessages(targetConv.messages || []);
      setCurrentReport('log');
      setReidReportData(null);
      setAnomalyReportData(null);
      setInputText('');
      setUploadedImage(null);
      saveConversationsToStorage(conversations, conversationId);
      console.log('[LLM_CHAT] 🔄 切换对话:', conversationId);
    }
  };

  // 清空当前会话的后端记忆，同时重置本地展示消息，保留 sessionId。
  const handleClearContext = async () => {
    if (isSending || isClearing) return;

    const currentConversation = conversations.find(c => c.id === currentConversationId);
    if (!currentConversation?.sessionId) return;

    setIsClearing(true);
    try {
      await clearAgentMemory(currentConversation.sessionId);
      setMessages([{
        ...createWelcomeMessage(),
        content: '上下文已清空，可以开始新的对话。',
      }]);
      setCurrentReport('log');
      setReidReportData(null);
      setAnomalyReportData(null);
      setInputText('');
      setUploadedImage(null);
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'ai',
        content: `清空上下文失败：${error.message}`,
      }]);
    } finally {
      setIsClearing(false);
    }
  };
  
  // 语音识别相关状态
  const [isRecording, setIsRecording] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(true);
  const [interimText, setInterimText] = useState(''); // 中间识别结果
  const recognitionRef = useRef(null);
  const baseTextRef = useRef(''); // 录音开始前的文本
  const handleSendRef = useRef(null); // 保存 handleSend 的引用
  const isStartingRef = useRef(false); // 防止重复启动的标志

  // 初始化语音识别
  useEffect(() => {
    if (!SpeechRecognition) {
      setSpeechSupported(false);
      console.warn('浏览器不支持语音识别');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true; // 持续识别
    recognition.interimResults = true; // 返回中间结果
    recognition.lang = 'zh-CN'; // 设置中文

    recognition.onresult = (event) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      // 更新输入框内容
      if (finalTranscript) {
        // 最终结果：追加到输入框
        setInputText(prev => prev + finalTranscript);
        setInterimText(''); // 清空中间结果
        baseTextRef.current = baseTextRef.current + finalTranscript;
      } else {
        // 中间结果：实时显示
        setInterimText(interimTranscript);
      }
    };

    recognition.onerror = (event) => {
      console.error('语音识别错误:', event.error);
      // 某些错误（如 no-speech）不会自动停止，需要手动停止
      if (event.error !== 'no-speech') {
        try {
          recognition.stop();
        } catch (e) {
          // 忽略停止时的错误
        }
      }
      setIsRecording(false);
      setInterimText('');
      isStartingRef.current = false; // 重置启动标志
    };

    recognition.onend = () => {
      // 确保状态更新
      setIsRecording(false);
      setInterimText('');
      isStartingRef.current = false; // 重置启动标志
    };

    recognitionRef.current = recognition;

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  // 切换语音录制
  const toggleVoiceRecording = () => {
    if (!speechSupported) {
      alert('您的浏览器不支持语音识别功能，请使用 Chrome 浏览器');
      return;
    }

    if (!recognitionRef.current) {
      console.warn('语音识别未初始化');
      return;
    }

    if (isRecording) {
      // 停止录制
      try {
        recognitionRef.current.stop();
        setIsRecording(false);
        setInterimText('');
        isStartingRef.current = false;
      } catch (error) {
        console.error('停止语音识别失败:', error);
        // 即使停止失败，也更新状态
        setIsRecording(false);
        setInterimText('');
        isStartingRef.current = false;
      }
    } else {
      // 如果正在启动中，忽略重复点击
      if (isStartingRef.current) {
        console.log('[LLM_CHAT] ⚠️ 正在启动中，忽略重复点击');
        return;
      }

      // 开始录制前，先确保识别已完全停止
      const startRecording = () => {
        try {
          // 先尝试停止（如果正在运行）
          try {
            recognitionRef.current.stop();
          } catch (e) {
            // 忽略停止错误，可能已经停止了
          }

          // 等待一小段时间确保完全停止
          setTimeout(() => {
            try {
              // 开始录制前，清空输入框
              setInputText('');
              baseTextRef.current = '';
              setInterimText('');
              
              isStartingRef.current = true;
              recognitionRef.current.start();
              setIsRecording(true);
            } catch (error) {
              console.error('启动语音识别失败:', error);
              setIsRecording(false);
              isStartingRef.current = false;
              
              // 如果是已经启动的错误，再等待一次后重试
              if (error.name === 'InvalidStateError' || error.message.includes('already started')) {
                setTimeout(() => {
                  try {
                    recognitionRef.current.stop();
                  } catch (e) {
                    // 忽略
                  }
                  setTimeout(() => {
                    try {
                      setInputText('');
                      baseTextRef.current = '';
                      setInterimText('');
                      isStartingRef.current = true;
                      recognitionRef.current.start();
                      setIsRecording(true);
                    } catch (retryError) {
                      console.error('重试启动语音识别失败:', retryError);
                      setIsRecording(false);
                      isStartingRef.current = false;
                    }
                  }, 200);
                }, 100);
              }
            }
          }, 100);
        } catch (error) {
          console.error('准备启动语音识别失败:', error);
          setIsRecording(false);
          isStartingRef.current = false;
        }
      };

      startRecording();
    }
  };

  // 计算显示的文本（包含中间识别结果）
  const displayText = isRecording && interimText ? inputText + interimText : inputText;

  // 滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // 消息更新时自动滚动到底部
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // 组件卸载时清除定时器
  useEffect(() => {
    return () => {
      if (autoSwitchTimerRef.current) {
        clearTimeout(autoSwitchTimerRef.current);
        autoSwitchTimerRef.current = null;
        console.log('[LLM_CHAT] ⏰ 组件卸载，清除自动切换定时器');
      }
    };
  }, []);

  // 处理发送消息
  const handleSend = async (promptOverride) => {
    if (isSending || isClearing) return;

    // 如果正在录音，先停止语音输入并合并中间文本
    const isSelectionAction = typeof promptOverride === 'string';
    let finalInputText = isSelectionAction ? promptOverride : inputText;
    const currentImage = isSelectionAction ? null : uploadedImage;
    
    if (isRecording && recognitionRef.current) {
      console.log('[LLM_CHAT] 🎤 检测到正在录音，先停止语音输入');
      try {
        // 先合并中间识别结果到最终文本（直接计算，不依赖状态更新）
        if (interimText && !isSelectionAction) {
          console.log('[LLM_CHAT] 📝 合并中间识别结果:', interimText);
          finalInputText = inputText + interimText;
          setInputText(finalInputText);
          baseTextRef.current = baseTextRef.current + interimText;
        }
        
        // 停止语音识别
        recognitionRef.current.stop();
        setIsRecording(false);
        setInterimText('');
        
        // 等待一小段时间确保识别完全停止
        await new Promise(resolve => setTimeout(resolve, 200));
      } catch (error) {
        console.error('[LLM_CHAT] ❌ 停止语音识别失败:', error);
        // 即使停止失败，也合并中间文本并更新状态
        if (interimText && !isSelectionAction) {
          finalInputText = inputText + interimText;
          setInputText(finalInputText);
          baseTextRef.current = baseTextRef.current + interimText;
        }
        setIsRecording(false);
        setInterimText('');
      }
    }
    
    console.log('[LLM_CHAT] 🔵 handleSend 被调用', {
      inputText: finalInputText,
      inputTextTrimmed: finalInputText.trim(),
      hasImage: !!currentImage,
      timestamp: new Date().toISOString()
    });

    if (!finalInputText.trim() && !currentImage) {
      console.log('[LLM_CHAT] ⚠️ 输入为空，返回');
      return;
    }

    const activeConversation = conversations.find(c => c.id === currentConversationId);
    if (!activeConversation?.sessionId) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'ai',
        content: '当前会话无效，请新建会话后重试。',
      }]);
      return;
    }
    
    // 如果有新的请求，重置自动切换定时器（如果当前是 personSearch 或 anomaly）
    if ((currentReport === 'personSearch' || currentReport === 'anomaly') && autoSwitchTimerRef.current) {
      clearTimeout(autoSwitchTimerRef.current);
      autoSwitchTimerRef.current = null;
      console.log('[LLM_CHAT] ⏰ 有新请求，清除之前的自动切换定时器');
    }

    const userText = finalInputText.trim();
    const requestPrompt = userText || '请描述这张图片的内容。';
    console.log('[LLM_CHAT] ✅ 准备发送消息:', userText);
    
    // 创建用户消息
    const newMessage = {
      id: Date.now(),
      type: 'user',
      content: userText,
      image: currentImage ? currentImage.base64 : null
    };

    setMessages(prev => [...prev, newMessage]);
    setInputText('');
    setUploadedImage(null);

    // 先添加一个"正在处理"的临时消息，如果请求成功会被替换
    const loadingMessageId = Date.now() + 1;
    const loadingMessage = {
      id: loadingMessageId,
      type: 'ai',
      content: '正在处理中...'
    };
    setMessages(prev => [...prev, loadingMessage]);
    setIsSending(true);
    
    console.log('[LLM_CHAT] 📝 已添加加载消息，准备发送请求');

    let streamedText = '';
    let pedestrianSearch = null;
    let businessResults = [];
    // 只有需要返回超分图片的请求使用普通接口，图片分析与文字共用流式接口。
    const isSuperResolutionRequest = /超分|super[\s_-]*resolution/i.test(requestPrompt);
    const isStreamingRequest = !isSuperResolutionRequest;
    const abortController = new AbortController();
    chatAbortControllerRef.current = abortController;

    try {
      console.log('[LLM_CHAT] 📤 发送请求到后端:', {
        prompt: requestPrompt,
        sessionId: activeConversation.sessionId,
        hasImage: !!currentImage?.file,
        timestamp: new Date().toISOString()
      });

      const data = !isStreamingRequest
        ? currentImage?.file
          ? await sendAgentImageMessage(
            requestPrompt,
            currentImage.file,
            activeConversation.sessionId,
            { signal: abortController.signal },
          )
          : await sendAgentMessage(requestPrompt, activeConversation.sessionId, {
              signal: abortController.signal,
            })
        : {
            ...await streamAgentMessage(
              requestPrompt,
              activeConversation.sessionId,
              ({ event, data: eventData }) => {
                if (event === 'status') {
                  const statusText = eventData?.stage === 'generating'
                    ? '正在生成回复...'
                    : '正在查询...';
                  setMessages(prev => prev.map(message => (
                    message.id === loadingMessageId && !streamedText
                      ? { ...message, content: statusText }
                      : message
                  )));
                } else if (event === 'delta' && typeof eventData?.text === 'string') {
                  streamedText += eventData.text;
                  setMessages(prev => prev.map(message => (
                    message.id === loadingMessageId
                      ? { ...message, content: streamedText }
                      : message
                  )));
                } else if (event === 'result') {
                  businessResults = collectAgentResults(eventData, businessResults);
                  setMessages(prev => prev.map(message => message.id === loadingMessageId
                    ? { ...message, businessResults, queryImage: currentImage?.base64 } : message));
                  const result = getPedestrianSearchResult(eventData);
                  if (result) {
                    pedestrianSearch = result;
                    setMessages(prev => prev.map(message => (
                      message.id === loadingMessageId
                        ? { ...message, content: streamedText, pedestrianSearch: result }
                        : message
                    )));
                  }
                }
              },
              { signal: abortController.signal, file: currentImage?.file },
            ),
            type: 'normal',
            text: streamedText,
          };
      
      businessResults = collectAgentResults(data, businessResults);
      pedestrianSearch = getPedestrianSearchResult(data) || pedestrianSearch;
      console.log('[LLM_CHAT] ✅ 请求完成:', {
        type: pedestrianSearch?.type || data.type,
        traceId: data.trace_id,
      });

      // 后端可能规范化或生成新的 session_id，必须回写到发起请求的会话。
      setConversations(prevConversations => {
        const updatedConversations = prevConversations.map(conversation => (
          conversation.id === activeConversation.id
            ? {
                ...conversation,
                sessionId: data.session_id,
                traceId: data.trace_id,
                updatedAt: new Date().toISOString(),
              }
            : conversation
        ));
        saveConversationsToStorage(updatedConversations, activeConversation.id);
        return updatedConversations;
      });
      
      const isSuperResolution = data.type === 'super_resolution';
      const superResolutionData = isSuperResolution && data.data && typeof data.data === 'object'
        ? data.data
        : null;
      // 将临时消息替换为最终消息；流式请求沿用同一个消息 ID，避免界面跳动。
      setMessages(prev => {
        const filtered = prev.filter(msg => msg.id !== loadingMessageId);
        return [...filtered, {
          id: loadingMessageId,
          type: 'ai',
          traceId: data.trace_id,
          content: isSuperResolution
            ? getSuperResolutionStatusMessage({ ...data, ...superResolutionData })
            : data.text || data.summary || '请求已处理完成。',
          resultImage: null,
          businessResults,
          queryImage: currentImage?.base64,
          pedestrianSearch,
          resultSize: superResolutionData?.result_size,
          originalSize: superResolutionData?.original_size,
          scale: superResolutionData?.scale,
        }];
      });

      // 根据 type 切换显示组件
      if (data.type === 'super_resolution') {
        // 超分结果在聊天消息中展示，不切换固定报告区域。
        setCurrentReport('log');
        if (autoSwitchTimerRef.current) {
          clearTimeout(autoSwitchTimerRef.current);
          autoSwitchTimerRef.current = null;
        }
      } else if (data.type === 'vad') {
        // 切换到异常报告
        setCurrentReport('anomaly');
        
        // 清除之前的定时器（如果有）
        if (autoSwitchTimerRef.current) {
          clearTimeout(autoSwitchTimerRef.current);
          autoSwitchTimerRef.current = null;
        }
        
        // 启动1分钟自动切换定时器
        console.log('[LLM_CHAT] ⏰ 启动1分钟自动切换定时器（切换到 anomaly）');
        autoSwitchTimerRef.current = setTimeout(() => {
          console.log('[LLM_CHAT] ⏰ 1分钟无新请求，自动切换回大模型日志监控');
          setCurrentReport('log');
          setAnomalyReportData(null);
          autoSwitchTimerRef.current = null;
        }, 60000); // 60秒 = 1分钟
        
        // 设置异常报告数据
        // 解析出现频率数据（按摄像头统计）
        const frequencyData = [
          { label: '摄像头1', value: data.tracklet?.camera_1 || 0 },
          { label: '摄像头2', value: data.tracklet?.camera_2 || 0 },
          { label: '摄像头3', value: data.tracklet?.camera_3 || 0 },
          { label: '摄像头4', value: data.tracklet?.camera_4 || 0 },
        ];

        // 解析 data 中的关键帧缩略图，按时间降序排序（最新的在左边）
        const thumbnails = [];
        if (data.data) {
          const trackletKeys = Object.keys(data.data).sort((a, b) => {
            const aTime = data.data[a].start_ts;
            const bTime = data.data[b].start_ts;
            // 降序排列：最新的时间在前（左边）
            return new Date(bTime) - new Date(aTime);
          });

          trackletKeys.forEach((key) => {
            const tracklet = data.data[key];
            if (tracklet.image) {
              // 处理 base64 图片
              let imageUrl = tracklet.image;
              
              // 如果已经是完整的 data URL，直接使用
              if (imageUrl.startsWith('data:image')) {
                // 确保格式正确：data:image/jpeg;base64,xxxxx
                if (!imageUrl.includes(',')) {
                  imageUrl = imageUrl.replace(';base64:', ';base64,');
                }
              } 
              // 如果是完整的 HTTP/HTTPS URL，直接使用
              else if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
                // 已经是完整 URL，直接使用
              }
              // 否则认为是 base64 字符串
              else {
                // 移除可能存在的空格和换行
                imageUrl = imageUrl.trim().replace(/\s/g, '');
                // 添加 data URL 前缀（即使以 / 开头也要添加前缀）
                imageUrl = `data:image/jpeg;base64,${imageUrl}`;
              }

              // 格式化时间标签
              let timeLabel = '';
              if (tracklet.start_ts) {
                try {
                  const date = new Date(tracklet.start_ts);
                  const hours = String(date.getHours()).padStart(2, '0');
                  const minutes = String(date.getMinutes()).padStart(2, '0');
                  const seconds = String(date.getSeconds()).padStart(2, '0');
                  timeLabel = `${hours}:${minutes}:${seconds} ${tracklet.camera || ''}`;
                } catch (e) {
                  timeLabel = tracklet.camera || '';
                }
              } else {
                timeLabel = tracklet.camera || '';
              }

              thumbnails.push({
                image: imageUrl,
                label: timeLabel,
                recording: tracklet.recording || null // 保存视频 URL
              });
            }
          });
        }

        console.log('[LLM_CHAT] 🚨 解析到的异常数据:', {
          date: data.date,
          frequencyData,
          summary: data.summary,
          thumbnailsCount: thumbnails.length
        });
        
        setAnomalyReportData({
          date: data.date || '',  // 日期，格式：2026年01月05日
          frequencyData,
          summary: data.summary || '暂无总结',
          thumbnails: thumbnails || []
        });
      } else if (data.type === 'reid') {
        // 切换到人员查找报告
        setCurrentReport('personSearch');
        
        // 清除之前的定时器（如果有）
        if (autoSwitchTimerRef.current) {
          clearTimeout(autoSwitchTimerRef.current);
          autoSwitchTimerRef.current = null;
        }
        
        // 启动1分钟自动切换定时器
        console.log('[LLM_CHAT] ⏰ 启动1分钟自动切换定时器（切换到 personSearch）');
        autoSwitchTimerRef.current = setTimeout(() => {
          console.log('[LLM_CHAT] ⏰ 1分钟无新请求，自动切换回大模型日志监控');
          setCurrentReport('log');
          setReidReportData(null);
          autoSwitchTimerRef.current = null;
        }, 60000); // 60秒 = 1分钟
        
        // 解析 tracklet 数据，构建柱状图数据
        const frequencyData = [
          { label: '摄像头1', value: data.tracklet?.camera_1 || 0 },
          { label: '摄像头2', value: data.tracklet?.camera_2 || 0 },
          { label: '摄像头3', value: data.tracklet?.camera_3 || 0 },
          { label: '摄像头4', value: data.tracklet?.camera_4 || 0 },
        ];

        // 解析 data 中的关键帧缩略图，按时间降序排序（最新的在左边）
        const thumbnails = [];
        if (data.data) {
          const trackletKeys = Object.keys(data.data).sort((a, b) => {
            const aTime = data.data[a].start_ts;
            const bTime = data.data[b].start_ts;
            // 降序排列：最新的时间在前（左边）
            return new Date(bTime) - new Date(aTime);
          });

          trackletKeys.forEach((key) => {
            const tracklet = data.data[key];
            if (tracklet.image) {
              // 处理 base64 图片
              let imageUrl = tracklet.image;
              
              // 如果已经是完整的 data URL，直接使用
              if (imageUrl.startsWith('data:image')) {
                // 确保格式正确：data:image/jpeg;base64,xxxxx
                if (!imageUrl.includes(',')) {
                  imageUrl = imageUrl.replace(';base64:', ';base64,');
                }
              } 
              // 如果是完整的 HTTP/HTTPS URL，直接使用
              else if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
                // 已经是完整 URL，直接使用
              }
              // 否则认为是 base64 字符串
              // 注意：base64 字符串可能以 / 开头（如 /9j/4AAQ...），这是 JPEG 的 base64 特征
              // 不能把它当作相对路径，需要添加 data URL 前缀
              else {
                // 移除可能存在的空格和换行
                imageUrl = imageUrl.trim().replace(/\s/g, '');
                // 添加 data URL 前缀（即使以 / 开头也要添加前缀）
                imageUrl = `data:image/jpeg;base64,${imageUrl}`;
              }
              
              console.log('[LLM_CHAT] 🖼️ 图片处理:', {
                key,
                originalLength: tracklet.image.length,
                originalPreview: tracklet.image.substring(0, 30),
                processedLength: imageUrl.length,
                hasPrefix: imageUrl.startsWith('data:image'),
                processedPreview: imageUrl.substring(0, 50) + '...'
              });

              // 格式化时间标签
              let timeLabel = '';
              if (tracklet.start_ts) {
                try {
                  const date = new Date(tracklet.start_ts);
                  const hours = String(date.getHours()).padStart(2, '0');
                  const minutes = String(date.getMinutes()).padStart(2, '0');
                  const seconds = String(date.getSeconds()).padStart(2, '0');
                  timeLabel = `${hours}:${minutes}:${seconds} ${tracklet.camera || ''}`;
                } catch (e) {
                  timeLabel = tracklet.camera || '';
                }
    } else {
                timeLabel = tracklet.camera || '';
              }

              thumbnails.push({
                image: imageUrl,
                label: timeLabel,
                recording: tracklet.recording || null // 保存视频 URL
              });
            }
          });
        }

        // 设置 ReID 报告数据
        // 从 person_names 中获取人名，如果没有则使用用户输入
        let personName = userText;
        if (data.person_names && Array.isArray(data.person_names) && data.person_names.length > 0) {
          personName = data.person_names[0]; // 使用第一个名字
        }
        
        console.log('[LLM_CHAT] 👤 解析到的人员名称:', personName);
        console.log('[LLM_CHAT] 📊 频率数据:', frequencyData);
        console.log('[LLM_CHAT] 📝 总结:', data.summary);
        console.log('[LLM_CHAT] 🖼️ 缩略图数量:', thumbnails.length);
        
        setReidReportData({
          name: personName,
          frequencyData,
          summary: data.summary || '暂无总结',
          thumbnails: thumbnails || []
        });
      } else if (pedestrianSearch || data.type === 'normal' || data.type === 'agent') {
        // 切换到普通日志报告
        setCurrentReport('log');
        setReidReportData(null);
        
        // 清除自动切换定时器
        if (autoSwitchTimerRef.current) {
          clearTimeout(autoSwitchTimerRef.current);
          autoSwitchTimerRef.current = null;
          console.log('[LLM_CHAT] ⏰ 清除自动切换定时器（切换到 normal）');
        }
      }
    } catch (error) {
      console.error('[LLM_CHAT] ❌ 发送请求失败:', error);
      console.error('[LLM_CHAT] 错误详情:', {
        message: error.message,
        errorCode: error.errorCode,
        traceId: error.traceId,
        stack: error.stack,
        name: error.name,
        cause: error.cause
      });
      
      const wasCancelled = abortController?.signal.aborted;
      const errorMessage = wasCancelled
        ? (streamedText ? `${streamedText}\n\n已停止生成。` : '已停止生成。')
        : `${streamedText ? `${streamedText}\n\n` : ''}请求失败${error.errorCode ? `（${error.errorCode}）` : ''}：${error.message}`
        + (error.traceId ? `（trace_id: ${error.traceId}）` : '');
      
      // 移除加载消息，添加错误消息
      setMessages(prev => {
        return prev.map(message => (
          message.id === loadingMessageId
            ? { ...message, content: errorMessage, stopped: wasCancelled }
            : message
        ));
      });
    } finally {
      if (chatAbortControllerRef.current === abortController) {
        chatAbortControllerRef.current = null;
      }
      setIsSending(false);
    }
  };

  const handleStopGenerating = () => {
    chatAbortControllerRef.current?.abort();
  };

  // 处理键盘事件
  const handleKeyDown = (e) => {
    console.log('[LLM_CHAT] ⌨️ 键盘事件:', {
      key: e.key,
      shiftKey: e.shiftKey,
      isRecording: isRecording,
      inputText: inputText,
      displayText: displayText,
      target: e.target.tagName
    });
    
    // 如果按的是回车键，无论当前焦点在哪里，都触发发送
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.stopPropagation();
      console.log('[LLM_CHAT] ⏎ Enter 键被按下，调用 handleSend');
      // handleSend 内部会处理停止语音的逻辑
      handleSend();
    }
  };

  // 全局键盘事件监听（用于捕获语音输入时的回车键）
  useEffect(() => {
    if (!isRecording) return;
    
    const handleGlobalKeyDown = (e) => {
      // 如果正在录音且按的是回车键，触发发送
      if (e.key === 'Enter' && !e.shiftKey) {
        // 如果焦点不在输入框上，也触发发送
        const activeElement = document.activeElement;
        const isInputFocused = activeElement?.tagName === 'INPUT' && activeElement?.type === 'text';
        
        if (!isInputFocused) {
          e.preventDefault();
          e.stopPropagation();
          console.log('[LLM_CHAT] 🎤 语音输入时按回车（焦点不在输入框），触发发送');
          // 使用最新的 handleSend
          const sendFn = handleSendRef.current;
          if (sendFn) {
            sendFn();
          }
        }
      }
    };
    
    // 只在录音时添加全局监听，使用捕获阶段确保优先处理
    window.addEventListener('keydown', handleGlobalKeyDown, true);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeyDown, true);
    };
  }, [isRecording]);
  
  // 更新 handleSend 的 ref
  useEffect(() => {
    handleSendRef.current = handleSend;
  }, [handleSend]);

  // 处理图片文件（只允许一张，重复上传覆盖之前的）。文件选择和剪贴板粘贴共用这条路径。
  const processImageFile = (file) => {
    if (!file) return false;

    // Agent 仅接受 JPEG、PNG、WebP，且单张图片不超过 10 MB。
    if (!SUPPORTED_IMAGE_TYPES.includes(file.type)) {
      console.warn('[LLM_CHAT] ⚠️ 文件不是图片格式:', file.type);
      alert('仅支持 JPEG、PNG 和 WebP 图片');
      return false;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      alert('图片文件不能超过 10 MB');
      return false;
    }
    
    const reader = new FileReader();
    reader.onload = (event) => {
      const base64String = event.target.result; // data:image/jpeg;base64,xxxxx
      
      // 覆盖之前的图片（只保留一张）
      const preview = new Image();
      preview.onload = () => {
        if (preview.width > 8192 || preview.height > 8192 || preview.width * preview.height > 25000000) {
          alert('图片尺寸过大：最长边不能超过 8192 像素，且总像素不能超过 2500 万');
          return;
        }

        setUploadedImage({
          id: Date.now(),
          name: file.name || `pasted-image-${Date.now()}.${file.type.split('/')[1] || 'png'}`,
          file,
          base64: base64String, // 完整的 data URL
          url: base64String // 用于预览
        });
        console.log('[LLM_CHAT] ✅ 图片上传成功:', {
          name: file.name,
          type: file.type,
          size: file.size,
          width: preview.width,
          height: preview.height,
          base64Length: base64String.length
        });
    };
      preview.onerror = () => {
        alert('图片无法解析，请重新选择图片');
      };
      preview.src = base64String;
      
    };
    
    reader.onerror = () => {
      console.error('[LLM_CHAT] ❌ 图片读取失败');
      alert('图片读取失败，请重试');
    };
    
    reader.readAsDataURL(file);
    
    return true;
  };

  // 处理图片上传（只允许一张，重复上传覆盖之前的）
  const handleImageUpload = (e) => {
    processImageFile(e.target.files?.[0]); // 只取第一张图片

    // 清空 input 以便重复上传同一文件
    e.target.value = '';
  };

  // 支持直接把剪贴板中的图片粘贴到对话输入框。
  const handleInputPaste = (e) => {
    if (isSending || isClearing) return;

    const clipboardItems = Array.from(e.clipboardData?.items || []);
    const imageItem = clipboardItems.find(item => item.kind === 'file' && item.type.startsWith('image/'));
    const file = imageItem?.getAsFile()
      || Array.from(e.clipboardData?.files || []).find(candidate => candidate.type.startsWith('image/'));
    if (!file) return;

    e.preventDefault();
    const extension = file.type === 'image/jpeg' ? 'jpg' : file.type.split('/')[1];
    const namedFile = file.name
      ? file
      : new File([file], `pasted-image-${Date.now()}.${extension}`, { type: file.type });
    processImageFile(namedFile);
  };

  // 删除已上传的图片
  const removeImage = () => {
    setUploadedImage(null);
  };

  // 触发文件选择
  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const pendingSelection = getPendingPedestrianSelection(messages);

  return (
    <div className={`${styles.container} flex-col`}>
      {/* 装饰线 */}
      <div 
        className={styles.decorLine}
        style={{ backgroundImage: `url(${lineDeco})` }}
      />
      
      {/* 标题栏 */}
      <div 
        className={`${styles.titleBar} flex-row`}
        style={{ backgroundImage: `url(${titleBarBg})` }}
      >
        <div 
          className={styles.titleIcon}
          style={{ backgroundImage: `url(${titleIcon})` }}
        />
        <span className={styles.titleText}>火眼金睛大模型</span>
        
        {/* 对话管理按钮 */}
        <div className={styles.conversationControls}>
          {/* 当前对话名字 */}
          {currentConversationId && (
            editingTitleId === currentConversationId ? (
              <input
                ref={titleInputRef}
                type="text"
                value={editingTitleValue}
                onChange={(e) => setEditingTitleValue(e.target.value)}
                onBlur={handleTitleSave}
                onKeyDown={handleTitleKeyDown}
                className={styles.titleInput}
                style={{
                  background: 'rgba(65, 177, 255, 0.2)',
                  border: '1px solid rgba(65, 177, 255, 0.5)',
                  borderRadius: '4px',
                  padding: '2px 8px',
                  color: '#FFFFFF',
                  fontSize: '20px',
                  fontFamily: 'PingFangSC-Medium',
                  fontWeight: 500,
                  outline: 'none',
                  minWidth: '100px',
                  maxWidth: '200px',
                }}
              />
            ) : (
              <span 
                className={styles.currentConversationTitle}
                onDoubleClick={() => handleTitleDoubleClick(currentConversationId)}
                title="双击编辑"
                style={{ cursor: 'pointer' }}
              >
                {conversations.find(c => c.id === currentConversationId)?.title || '新对话'}
              </span>
            )
          )}
          
          {/* 对话列表下拉菜单（hover显示） */}
          {conversations.length > 1 && (
            <div 
              className={styles.conversationDropdown}
              onMouseEnter={() => {
                // 清除之前的延迟隐藏定时器
                if (conversationDropdownTimerRef.current) {
                  clearTimeout(conversationDropdownTimerRef.current);
                  conversationDropdownTimerRef.current = null;
                }
                setShowDropdown(true);
              }}
              onMouseLeave={() => {
                // 延迟0.5秒隐藏
                conversationDropdownTimerRef.current = setTimeout(() => {
                  setShowDropdown(false);
                }, 500);
              }}
            >
              <button 
                className={styles.conversationListBtn}
                title="查看对话列表"
                disabled={isSending || isClearing}
              >
                📋
              </button>
              {showDropdown && (
                <div className={styles.conversationDropdownMenu}>
                  {conversations.map(conv => (
                    <div
                      key={conv.id}
                      className={`${styles.conversationItem} ${conv.id === currentConversationId ? styles.active : ''}`}
                      onClick={() => {
                        if (editingTitleId !== conv.id) {
                          handleSwitchConversation(conv.id);
                          setShowDropdown(false);
                        }
                      }}
                      title={conv.title}
                    >
                      {editingTitleId === conv.id ? (
                        <input
                          type="text"
                          value={editingTitleValue}
                          onChange={(e) => setEditingTitleValue(e.target.value)}
                          onBlur={handleTitleSave}
                          onKeyDown={handleTitleKeyDown}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            background: 'rgba(65, 177, 255, 0.2)',
                            border: '1px solid rgba(65, 177, 255, 0.5)',
                            borderRadius: '4px',
                            padding: '4px 8px',
                            color: '#FFFFFF',
                            fontSize: '14px',
                            fontFamily: 'PingFangSC-Regular',
                            outline: 'none',
                            flex: 1,
                            minWidth: 0,
                          }}
                        />
                      ) : (
                        <span 
                          className={styles.conversationTitle}
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            handleTitleDoubleClick(conv.id);
                          }}
                          title="双击编辑"
                          style={{ cursor: 'pointer', flex: 1 }}
                        >
                          {conv.title}
                        </span>
                      )}
                      <button
                        className={styles.deleteConvBtn}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteConversation(conv.id);
                        }}
                        title="删除对话"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          
          {/* 新建对话按钮 */}
          <button 
            className={styles.addConversationBtn}
            onClick={handleAddConversation}
            title="新建对话"
            disabled={isSending || isClearing}
          >
            +
          </button>

          {/* 清空后端上下文，保留当前会话 ID。 */}
          {currentConversationId && (
            <button
              className={styles.clearContextBtn}
              onClick={handleClearContext}
              title="清空上下文"
              aria-label="清空上下文"
              disabled={isSending || isClearing}
            >
              {isClearing ? <span className={styles.controlSpinner} /> : <Eraser size={16} />}
            </button>
          )}
          
          {/* 删除当前对话按钮 */}
          {currentConversationId && conversations.length > 1 && (
            <button 
              className={styles.deleteConversationBtn}
              onClick={() => handleDeleteConversation(currentConversationId)}
              title="删除当前对话"
              disabled={isSending || isClearing}
            >
              ×
            </button>
          )}
        </div>
        
        <div 
          className={styles.cornerDeco}
          style={{ backgroundImage: `url(${cornerDeco})` }}
        />
      </div>
      
      {/* 内容区域 */}
      <div className={styles.contentContainer}>
        {/* 消息列表区域 - 可滚动 */}
        <div className={styles.messagesArea}>
          {messages.map((msg) => (
            <div 
              key={msg.id} 
              className={`${styles.messageRow} ${msg.type === 'user' ? styles.userRow : styles.aiRow}`}
            >
              {msg.type === 'ai' && (
                <img className={styles.avatar} src={aiAvatar} alt="AI" />
              )}
              
              <div className={styles.messageContent}>
                {/* 显示图片 */}
                {msg.image && (
                  <div className={styles.messageImages}>
                      <img 
                      src={msg.image} 
                      alt="上传的图片"
                        className={styles.messageImage}
                      />
                  </div>
                )}
                
                {/* 显示文字 */}
                {msg.content && (
                  <div className={`${styles.messageBubble} ${msg.type === 'user' ? styles.userBubble : styles.aiBubble}`}>
                    {msg.type === 'ai' ? (
                      <div className={`${styles.messageText} ${styles.aiText} ${styles.markdownContent}`}>
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            a: ({ children, ...props }) => (
                              <a {...props} target="_blank" rel="noopener noreferrer">
                                {children}
                              </a>
                            ),
                          }}
                        >
                          {String(msg.content)}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <span className={`${styles.messageText} ${styles.userText}`}>
                        {msg.content}
                      </span>
                    )}
                  </div>
                )}

                {msg.pedestrianSearch && (
                  <PedestrianSearchResult
                    result={msg.pedestrianSearch}
                    inactive={pendingSelection !== msg}
                    disabled={isSending || isClearing || !!uploadedImage}
                    onSelect={candidateId => handleSend(`选择${candidateId}`)}
                    onCancel={() => handleSend('取消选择')}
                  />
                )}

                {msg.businessResults?.length > 0 && <AgentBusinessResults results={msg.businessResults} queryImage={msg.queryImage} />}

                {msg.resultImage && (
                  <div className={styles.superResolutionResult}>
                    <img
                      src={msg.resultImage}
                      alt="超分结果"
                      className={styles.superResolutionImage}
                    />
                    {(msg.resultSize || msg.scale) && (
                      <span className={styles.superResolutionMeta}>
                        {msg.resultSize && `${msg.resultSize[0]}×${msg.resultSize[1]}`}
                        {msg.resultSize && msg.scale ? ' · ' : ''}
                        {msg.scale ? `${msg.scale}倍` : ''}
                      </span>
                    )}
                    <button
                      type="button"
                      className={styles.downloadResultButton}
                      onClick={() => downloadImage(msg.resultImage)}
                    >
                      <Download size={14} aria-hidden="true" />
                      下载结果
                    </button>
                  </div>
                )}
              </div>
              
              {msg.type === 'user' && (
                <img className={styles.avatar} src={userAvatar} alt="User" />
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        
        {/* 固定报告区域 - 根据指令切换不同报告 */}
        <div className={styles.fixedReportSection}>
          {currentReport === 'personSearch' && reidReportData && (
            <PersonSearchReport data={reidReportData} />
          )}
          {currentReport === 'anomaly' && anomalyReportData && (
            <AnomalyReport data={anomalyReportData} />
          )}
          {currentReport === 'log' && (
            <LogReport />
          )}
        </div>
        
        {/* 输入区域 */}
        <div className={styles.inputSection}>
          {/* 已上传图片预览（只显示一张） */}
          {uploadedImage && (
            <div className={styles.uploadedImagesRow}>
              <div className={styles.uploadedImageWrapper}>
                <img src={uploadedImage.url} alt={uploadedImage.name} className={styles.uploadedImage} />
                  <button 
                    className={styles.removeImageBtn}
                  onClick={removeImage}
                  >
                    ×
                  </button>
                </div>
            </div>
          )}
          
          <div className={styles.inputContainer}>
            {/* 隐藏的文件输入 */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageUpload}
              className={styles.hiddenFileInput}
            />
            
            {/* 文本输入框 */}
            <input
              type="text"
              className={`${styles.textInput} ${isRecording ? styles.recording : ''}`}
              placeholder={isRecording ? '正在聆听...' : '请输入指令或语言'}
              value={displayText}
              onChange={(e) => {
                if (!isRecording) {
                  console.log('[LLM_CHAT] 📝 输入框内容变化:', e.target.value);
                  setInputText(e.target.value);
                }
              }}
              onPaste={handleInputPaste}
              onKeyDown={handleKeyDown}
              readOnly={isRecording}
              disabled={isClearing}
            />
            
            {/* 工具栏 - 图标按钮 */}
            <div className={styles.inputToolbar}>
              {/* 上传图片按钮 */}
              <button
                className={styles.toolButton}
                onClick={triggerFileInput}
                disabled={isSending || isClearing}
              >
                <img src={cameraIcon} alt="上传图片" className={styles.toolIcon} />
              </button>
              
              {/* 语音按钮 */}
              <button 
                className={`${styles.toolButton} ${isRecording ? styles.recording : ''}`}
                onClick={toggleVoiceRecording}
                onKeyDown={(e) => {
                  // 如果正在录音且按回车，触发发送而不是切换录音
                  if (isRecording && e.key === 'Enter') {
                    e.preventDefault();
                    e.stopPropagation();
                    handleSend();
                  }
                }}
                title={isRecording ? '点击停止录音' : '点击开始语音输入'}
                tabIndex={-1} // 防止通过 Tab 键聚焦
                disabled={isSending || isClearing}
              >
                <img src={micIcon} alt="语音" className={styles.toolIcon} />
                {isRecording && <span className={styles.recordingIndicator} />}
              </button>
              
              {/* 发送按钮 */}
              <button 
                className={`${styles.sendButton} ${isSending ? styles.sending : ''}`}
                onClick={isSending ? handleStopGenerating : handleSend}
                style={{ backgroundImage: `url(${sendIcon})` }}
                disabled={isClearing || (isSending && !chatAbortControllerRef.current)}
                title={isSending ? '停止生成' : '发送'}
                aria-label={isSending ? '停止生成' : '发送'}
              >
                {isSending && <span className={styles.sendingSpinner} />}
              </button>
            </div>
          </div>
        </div>
        
        {/* 右下角装饰点 */}
        <div className={styles.dotDecor}>
          <div className={styles.dot} />
        </div>
      </div>
    </div>
  );
}

export default RightSidebar;
