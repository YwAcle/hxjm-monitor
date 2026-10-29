import React from 'react';
import styles from './ModelAccess.module.css';

// 导入图片资源
import sectionBg from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bg_samll.png';
import lineDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_bottom_small.png';
import titleIcon from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_arrow.png';
import cornerDeco from '../../../../view/lanhu_shipinjiankonguisheji1230/assets/img/header_top_small.png';

function ModelAccess() {
  return (
    <div className={`${styles.container} flex-col`}>
      {/* 标题区域 */}
      <div 
        className={`${styles.headerSection} flex-col`}
        style={{ backgroundImage: `url(${sectionBg})` }}
      >
        <div 
          className={styles.decorLine}
          style={{ backgroundImage: `url(${lineDeco})` }}
        />
        <div className={`${styles.titleRow} flex-row justify-between`}>
          <div 
            className={styles.titleIcon}
            style={{ backgroundImage: `url(${titleIcon})` }}
          />
          <span className={styles.titleText}>接入小模型</span>
        </div>
      </div>
      
      {/* 词云区域 */}
      <div className={`${styles.wordCloudContainer} flex-col justify-end`}>
        <div className={`${styles.wordCloudRow} flex-row`}>
          <span className={styles.textFaceRes}>人脸超分辨率</span>
          <span className={styles.textVlm}>视觉语言大模型</span>
          <span className={styles.textAreaIntrusion}>区域闯入</span>
          <span className={styles.textXx1}></span>
          <span className={styles.textXx2}></span>
          <span className={styles.textFallDetect}>摔倒检测</span>
          <span className={styles.textLoitering}>徘徊异常</span>
          <span className={styles.textSmoke}>烟雾检测</span>
        </div>
        
        {/* 右下角装饰点 */}
        <div className={`${styles.dotDecor} flex-row`}>
          <div className={styles.dot} />
        </div>
        
        {/* 上半部分词云 */}
        <div className={`${styles.topWordCloud} flex-row justify-between`}>
          <div className={`${styles.leftWords} flex-col justify-between`}>
            <div className={`${styles.wordsRow1} flex-row`}>
              <span className={styles.textXx3}></span>
              <span className={styles.textFightDetect}>打架检测</span>
              <span className={styles.textVoice}>语音交互</span>
              <span className={styles.textCrowd}>人员聚集</span>
              <span className={styles.textXx4}></span>
            </div>
            <div className={`${styles.wordsRow2} flex-row justify-between`}>
              <span className={styles.textXx5}></span>
              <span className={styles.textReid}>行人重识别</span>
            </div>
          </div>
          <div className={`${styles.rightWords} flex-col`}>
            <span className={styles.textAgent}>智能体</span>
            <span className={styles.textXx6}></span>
            <span className={styles.textXx7}></span>
          </div>
        </div>
        
        {/* 角落装饰 */}
        <div 
          className={styles.cornerDeco}
          style={{ backgroundImage: `url(${cornerDeco})` }}
        />
      </div>
    </div>
  );
}

export default ModelAccess;

