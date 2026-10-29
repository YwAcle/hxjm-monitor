import React, { useState, useEffect } from 'react';
import styles from './Header.module.css';
import BusinessPanel from '../BusinessPanel/BusinessPanel';

// 导入图片资源
import headerBg from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPng927056555a45da5d4a56e0fc6257f591053eac029bf9acede2db9b0f571a5acd.png';
import headerBg2 from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPngc3031fc1123d1b010190460a04384359b42254dee5d8be030a4bb0ae38107df0.png';
import headerBg3 from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPngd6d401097b4d283db02035920dd34e7202c84767722521b18b58f2c6419042d6.png';
import headerBg4 from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPng246b603d7ea1919d420f2d104ee4b1edaca32555ec831a6aadd679d9b226b5b9.png';
import decorLeft from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/3a8dc036a0174c6c9d08b03e26bff289_mergeImage.png';
import decorRight from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/2a20b6a0f8314d17934ff351dae91a5d_mergeImage.png';
import decorCenter from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/3d9ebf05a59046088f26d624607ba4a5_mergeImage.png';
import headerDecoLeft from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPngefa0ccae68c28159fefec7657a5dad44524f1e8bcb8683a8c52ea57e6d28f29a.png';
import headerDecoRight from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/SketchPng1601612d8f34d94d0897084acce04a010f194009abb1f9bd4155ac0c17a5fd3a.png';
import titleImage from '../../view/lanhu_shipinjiankonguisheji1230/assets/img/标题文字@3x.png';

function Header() {
  const [currentTime, setCurrentTime] = useState(new Date());

  // 更新时间
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // 格式化时间：YYYY-MM-DD HH:mm:ss
  const formatTime = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  };

  return (
    <>
      {/* 顶部装饰条 */}
      <div className={`${styles.imageWrapper} flex-row justify-between`}>
        <img className={styles.imageLeft} src={headerDecoLeft} alt="" />
        <img className={styles.imageRight} src={headerDecoRight} alt="" />
      </div>
      
      {/* 主标题区域 - 绝对定位在顶部 */}
      <div className={`${styles.headerContainer} flex-col`}>
        <BusinessPanel />
        <div className={`${styles.headerBlock} flex-col`}>
          <div className={`${styles.headerRow} flex-row`}>
            <div 
              className={styles.decorLeft}
              style={{ backgroundImage: `url(${decorLeft})` }}
            />
            <div className={`${styles.titleWrapper} flex-col`}>
              <div 
                className={`${styles.titleBg} flex-col`}
                style={{ backgroundImage: `url(${headerBg4})` }}
              >
                <div 
                  className={styles.titleInner}
                  style={{ backgroundImage: `url(${decorCenter})` }}
                />
              </div>
              <img className={styles.title} src={titleImage} alt="慧心极目·火眼金睛视频监控平台" />
            </div>
            <div 
              className={styles.decorRight}
              style={{ backgroundImage: `url(${decorRight})` }}
            />
            <span className={styles.currentTime}>{formatTime(currentTime)}</span>
          </div>
        </div>
      </div>
    </>
  );
}

export default Header;

