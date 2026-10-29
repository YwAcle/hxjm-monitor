'use strict';

import React, { Component } from 'react';
import { Switch, NavBar, Checkbox, Radio, Input, Tabs, TabBar, Badge } from 'antd-mobile';

import styles from './assets/index.module.css';

const print = function (value) {};
class DDS_lanhupage_0 extends Component {
  state = {};
  setValue(val) {}
  render() {
    return (
      <div className={`${styles.page} flex-col`}>
        <div className={`${styles['box_1']} flex-col`}>
          <div className={`${styles['image-wrapper_1']} flex-row justify-between`}>
            <img
              className={`${styles['image_1']}`}
              src={
                require('./assets/img/SketchPngefa0ccae68c28159fefec7657a5dad44524f1e8bcb8683a8c52ea57e6d28f29a.png')
              }
            />
            <img
              className={`${styles['image_2']}`}
              src={
                require('./assets/img/SketchPng1601612d8f34d94d0897084acce04a010f194009abb1f9bd4155ac0c17a5fd3a.png')
              }
            />
          </div>
          <div className={`${styles['section_1']} flex-row justify-between`}>
            <div className={`${styles['box_2']} flex-col`}>
              <div className={`${styles['box_3']} flex-col`} />
              <div className={`${styles['box_4']} flex-row`}>
                <div className={`${styles['group_1']} flex-col`} />
                <span className={`${styles['text_1']}`}>平台概览</span>
              </div>
              <div className={`${styles['box_5']} flex-col justify-end`}>
                <div className={`${styles['group_2']} flex-row`}>
                  <img
                    className={`${styles['image_3']}`}
                    src={
                      require('./assets/img/SketchPngd2ecebcb5c020310ce990b023cfce68186ac5a5f7d5475d4ea85ca9310446ac9.png')
                    }
                  />
                  <div className={`${styles['group_3']} flex-col justify-between`}>
                    <span className={`${styles['text_2']}`}>接入设备</span>
                    <div className={`${styles['text-wrapper_1']}`}>
                      <span className={`${styles['text_3']}`}>23</span>
                      <span className={`${styles['text_4']}`}></span>
                      <span className={`${styles['text_5']}`}>个</span>
                    </div>
                  </div>
                  <img
                    className={`${styles['image_4']}`}
                    src={
                      require('./assets/img/SketchPng07e6bfdac7774c81062722db2bb922c92189d0033f7a7c677df52357bff27a57.png')
                    }
                  />
                  <div className={`${styles['group_4']} flex-col justify-between`}>
                    <span className={`${styles['text_6']}`}>AI分析</span>
                    <div className={`${styles['text-wrapper_2']}`}>
                      <span className={`${styles['text_7']}`}>2</span>
                      <span className={`${styles['text_8']}`}></span>
                      <span className={`${styles['text_9']}`}>万</span>
                    </div>
                  </div>
                  <img
                    className={`${styles['image_5']}`}
                    src={
                      require('./assets/img/SketchPngf913a41952c92c585ef152ff0939e11e662e884d838bec523959dab87ff83d13.png')
                    }
                  />
                  <div className={`${styles['group_5']} flex-col justify-between`}>
                    <span className={`${styles['text_10']}`}>异常检测</span>
                    <div className={`${styles['text-wrapper_3']}`}>
                      <span className={`${styles['text_11']}`}>15</span>
                      <span className={`${styles['text_12']}`}></span>
                      <span className={`${styles['text_13']}`}>次</span>
                    </div>
                  </div>
                </div>
                <div className={`${styles['group_6']} flex-row`}>
                  <div className={`${styles['box_6']} flex-col`} />
                </div>
                <div className={`${styles['group_7']} flex-col`} />
              </div>
              <div className={`${styles['box_7']} flex-row justify-between`}>
                <div className={`${styles['box_8']} flex-col`}>
                  <div className={`${styles['section_2']} flex-col`} />
                  <div className={`${styles['section_3']} flex-row justify-between`}>
                    <div className={`${styles['block_1']} flex-col`} />
                    <span className={`${styles['text_14']}`}>接入小模型</span>
                  </div>
                </div>
                <div className={`${styles['box_9']} flex-col`}>
                  <div className={`${styles['group_8']} flex-col`} />
                  <div className={`${styles['group_9']} flex-row justify-between`}>
                    <div className={`${styles['block_2']} flex-col`} />
                    <span className={`${styles['text_15']}`}>异常事件统计</span>
                  </div>
                  <div className={`${styles['group_10']} flex-col`} />
                </div>
              </div>
              <div className={`${styles['box_10']} flex-row justify-between`}>
                <div className={`${styles['group_11']} flex-col justify-end`}>
                  <div className={`${styles['text-wrapper_4']} flex-row`}>
                    <span className={`${styles['text_16']}`}>人脸超分辨率</span>
                    <span className={`${styles['text_17']}`}>视觉语言大模型</span>
                    <span className={`${styles['text_18']}`}>区域闯入</span>
                    <span className={`${styles['text_19']}`}>XX</span>
                    <span className={`${styles['text_20']}`}>XX</span>
                    <span className={`${styles['text_21']}`}>摔倒检测</span>
                    <span className={`${styles['text_22']}`}>徘徊异常</span>
                    <span className={`${styles['text_23']}`}>烟雾检测</span>
                  </div>
                  <div className={`${styles['section_4']} flex-row`}>
                    <div className={`${styles['section_5']} flex-col`} />
                  </div>
                  <div className={`${styles['section_6']} flex-row justify-between`}>
                    <div className={`${styles['group_12']} flex-col justify-between`}>
                      <div className={`${styles['text-wrapper_5']} flex-row`}>
                        <span className={`${styles['text_24']}`}>XX</span>
                        <span className={`${styles['text_25']}`}>打架检测</span>
                        <span className={`${styles['text_26']}`}>语音交互</span>
                        <span className={`${styles['text_27']}`}>人员聚集</span>
                        <span className={`${styles['text_28']}`}>XX</span>
                      </div>
                      <div className={`${styles['text-wrapper_6']} flex-row justify-between`}>
                        <span className={`${styles['text_29']}`}>XX</span>
                        <span className={`${styles['text_30']}`}>行人重识别</span>
                      </div>
                    </div>
                    <div className={`${styles['text-wrapper_7']} flex-col`}>
                      <span className={`${styles['text_31']}`}>智能体</span>
                      <span className={`${styles['text_32']}`}>XX</span>
                      <span className={`${styles['text_33']}`}>XX</span>
                    </div>
                  </div>
                  <div className={`${styles['section_7']} flex-col`} />
                </div>
                <div className={`${styles['group_13']} flex-col`}>
                  <div className={`${styles['box_11']} flex-row`}>
                    <div className={`${styles['box_12']} flex-col`} />
                    <span className={`${styles['text_34']}`}>打架监测</span>
                    <span className={`${styles['text_35']}`}>23</span>
                  </div>
                  <div className={`${styles['box_13']} flex-row`}>
                    <div className={`${styles['block_3']} flex-col`} />
                    <span className={`${styles['text_36']}`}>徘徊异常</span>
                    <span className={`${styles['text_37']}`}>23</span>
                  </div>
                  <div className={`${styles['box_14']} flex-row`}>
                    <div className={`${styles['box_15']} flex-col`} />
                    <span className={`${styles['text_38']}`}>摔倒监测</span>
                    <span className={`${styles['text_39']}`}>23</span>
                  </div>
                  <div className={`${styles['box_16']} flex-row justify-between`}>
                    <div className={`${styles['image-text_1']} flex-row justify-between`}>
                      <div className={`${styles['group_14']} flex-col`} />
                      <span className={`${styles['text-group_1']}`}>陌生人预警</span>
                    </div>
                    <span className={`${styles['text_40']}`}>23</span>
                  </div>
                  <div className={`${styles['box_17']} flex-col`} />
                </div>
              </div>
              <div className={`${styles['box_18']} flex-col`} />
              <div className={`${styles['box_19']} flex-row`}>
                <div className={`${styles['section_8']} flex-col`} />
                <span className={`${styles['text_41']}`}>行人身份认证</span>
                <div className={`${styles['section_9']} flex-row`}>
                  <span className={`${styles['text_42']}`}>今日总人流量</span>
                  <div className={`${styles['text-wrapper_8']}`}>
                    <span className={`${styles['text_43']}`}>18</span>
                    <span className={`${styles['text_44']}`}>人</span>
                  </div>
                </div>
              </div>
              <div className={`${styles['box_20']} flex-col justify-end`}>
                <div className={`${styles['text-wrapper_9']} flex-row`}>
                  <span className={`${styles['text_45']}`}>今日人流量</span>
                </div>
                <div className={`${styles['group_15']} flex-row justify-between`}>
                  <span className={`${styles['text_46']}`}>50</span>
                  <img
                    className={`${styles['image_6']}`}
                    src={
                      require('./assets/img/SketchPng5d562d862454b291d35e94db508b0d8482739d2fdda2873bc61186a5404a9d8d.png')
                    }
                  />
                </div>
                <div className={`${styles['group_16']} flex-row justify-between`}>
                  <span className={`${styles['text_47']}`}>40</span>
                  <img
                    className={`${styles['image_7']}`}
                    src={
                      require('./assets/img/SketchPng411f9cc643c1b350c820c373c052cc72d69fd8681d3ee0c57787ca542c4066a5.png')
                    }
                  />
                </div>
                <div className={`${styles['group_17']} flex-row justify-between`}>
                  <div className={`${styles['text-group_2']} flex-col justify-between`}>
                    <span className={`${styles['text_48']}`}>30</span>
                    <span className={`${styles['text_49']}`}>20</span>
                  </div>
                  <div className={`${styles['image-wrapper_2']} flex-col justify-between`}>
                    <img
                      className={`${styles['image_8']}`}
                      src={
                        require('./assets/img/SketchPng99a7e4400766b13efb36f954dd0f377a803a8018facf18e8308a4cc79fe3c0e2.png')
                      }
                    />
                    <img
                      className={`${styles['image_9']}`}
                      src={
                        require('./assets/img/SketchPng3d776e4c91d6ac1091974fe7835018cf6427d24acf227a9b3acf377a2a169877.png')
                      }
                    />
                  </div>
                </div>
                <div className={`${styles['group_18']} flex-row justify-between`}>
                  <div className={`${styles['text-group_3']} flex-col justify-between`}>
                    <span className={`${styles['text_50']}`}>10</span>
                    <span className={`${styles['text_51']}`}>0</span>
                  </div>
                  <div className={`${styles['box_21']} flex-col`}>
                    <img
                      className={`${styles['image_10']}`}
                      src={
                        require('./assets/img/SketchPng221142f7f6ccd0c02b548c2e5df9761bc800e397494f5745e6fa2fe589eb54f9.png')
                      }
                    />
                    <div className={`${styles['image-wrapper_3']} flex-row justify-between`}>
                      <img
                        className={`${styles['thumbnail_1']}`}
                        src={
                          require('./assets/img/SketchPnge73cd6a02481eaa1314ee8cc47305cbba99525cc1a2024a6021a4bc3fde4bab3.png')
                        }
                      />
                      <img
                        className={`${styles['thumbnail_2']}`}
                        src={
                          require('./assets/img/SketchPng23812f336d305678df7334642d6679db931d26e163317bd014a256b89a3cf52b.png')
                        }
                      />
                      <img
                        className={`${styles['thumbnail_3']}`}
                        src={
                          require('./assets/img/SketchPngd1ad686eec9e59c465d1b15ffa16d6cf1859ce34d73a2c89aca4d28a477372a5.png')
                        }
                      />
                      <img
                        className={`${styles['thumbnail_4']}`}
                        src={
                          require('./assets/img/SketchPngd5d58223d66c984620716d197b394ce5abeb837bbc47c5e99497fad3ad1846a3.png')
                        }
                      />
                      <img
                        className={`${styles['thumbnail_5']}`}
                        src={
                          require('./assets/img/SketchPngb047de5769d40dc3fc2ee1c1b076e7cd67073ca2e53b267711754fd63071e731.png')
                        }
                      />
                      <img
                        className={`${styles['thumbnail_6']}`}
                        src={
                          require('./assets/img/SketchPng3aae9b8c40ff820f38d93b6058418a0c4d97d964c0838684dbd4dd80e3811064.png')
                        }
                      />
                      <img
                        className={`${styles['thumbnail_7']}`}
                        src={
                          require('./assets/img/SketchPng473c9da3001e42f073e7e4a795cb816e31210d0460a325a202950ceb2463a1be.png')
                        }
                      />
                    </div>
                    <div className={`${styles['text-wrapper_10']} flex-row`}>
                      <span className={`${styles['text_52']}`}>10:50</span>
                      <span className={`${styles['text_53']}`}>12:50</span>
                      <span className={`${styles['text_54']}`}>12:50</span>
                      <span className={`${styles['text_55']}`}>12:50</span>
                      <span className={`${styles['text_56']}`}>14:50</span>
                      <span className={`${styles['text_57']}`}>12:50</span>
                      <span className={`${styles['text_58']}`}>16:50</span>
                    </div>
                  </div>
                </div>
                <div className={`${styles['group_19']} flex-row justify-between`}>
                  <div className={`${styles['box_22']} flex-col`} />
                  <span className={`${styles['text_59']}`}>行人身份信息</span>
                  <div className={`${styles['box_23']} flex-col`} />
                </div>
                <div className={`${styles['group_20']} flex-row`}>
                  <div className={`${styles['block_4']} flex-col`} />
                  <div className={`${styles['text-wrapper_11']} flex-col`}>
                    <span className={`${styles['text_60']}`}>张嘉豪</span>
                    <span className={`${styles['text_61']}`}>24/男/学生</span>
                    <span className={`${styles['text_62']}`}>2025-12-21&nbsp;&nbsp;08:47:51</span>
                  </div>
                  <div className={`${styles['block_5']} flex-col`} />
                  <div className={`${styles['text-wrapper_12']} flex-col`}>
                    <span className={`${styles['text_63']}`}>李坤鸿</span>
                    <span className={`${styles['text_64']}`}>25/男/学生</span>
                    <span className={`${styles['text_65']}`}>2025-12-20&nbsp;&nbsp;10:47:23</span>
                  </div>
                </div>
                <div className={`${styles['group_21']} flex-row`}>
                  <div className={`${styles['group_22']} flex-col`} />
                  <div className={`${styles['text-wrapper_13']} flex-col`}>
                    <span className={`${styles['text_66']}`}>况长江</span>
                    <span className={`${styles['text_67']}`}>25/男/学生</span>
                    <span className={`${styles['text_68']}`}>2025-12-25&nbsp;&nbsp;13:20:47</span>
                  </div>
                  <div className={`${styles['group_23']} flex-col`} />
                  <div className={`${styles['text-wrapper_14']} flex-col`}>
                    <span className={`${styles['text_69']}`}>张雨朦</span>
                    <span className={`${styles['text_70']}`}>23/女/学生</span>
                    <span className={`${styles['text_71']}`}>2025-12-25&nbsp;&nbsp;09:40:25</span>
                  </div>
                </div>
                <div className={`${styles['group_24']} flex-row`}>
                  <div className={`${styles['box_24']} flex-col`} />
                </div>
                <img
                  className={`${styles['image_11']}`}
                  src={
                    require('./assets/img/SketchPng1d513bb5ea0ab06ca3abec2574c14452515f42d497964e491201914f7ae96917.png')
                  }
                />
                <img
                  className={`${styles['image_12']}`}
                  src={
                    require('./assets/img/SketchPnge9b67bad2225667885af5471b4abb5ee54794615087abcec12272dcfdf85d359.png')
                  }
                />
                <img
                  className={`${styles['image_13']}`}
                  src={
                    require('./assets/img/SketchPng5002b8163d1e7f3d2b9374df0e17d52226e0423dbd2132e20fd7dbd616d08f6c.png')
                  }
                />
                <img
                  className={`${styles['image_14']}`}
                  src={
                    require('./assets/img/SketchPngedb2e25dcf982bad3511a8f448c067539f1e1e854d02070826d2e82610259861.png')
                  }
                />
              </div>
            </div>
            <div className={`${styles['box_25']} flex-col`}>
              <div className={`${styles['block_6']} flex-row justify-between`}>
                <div className={`${styles['section_10']} flex-col`}>
                  <div className={`${styles['block_7']} flex-row`}>
                    <span className={`${styles['text_72']}`}>摄像头001</span>
                    <div className={`${styles['box_26']} flex-col`} />
                  </div>
                </div>
                <div className={`${styles['section_11']} flex-col`}>
                  <div className={`${styles['box_27']} flex-row`}>
                    <span className={`${styles['text_73']}`}>摄像头002</span>
                    <div className={`${styles['group_25']} flex-col`} />
                  </div>
                </div>
              </div>
              <div className={`${styles['block_8']} flex-row justify-between`}>
                <div className={`${styles['section_12']} flex-col`}>
                  <div className={`${styles['section_13']} flex-row`}>
                    <div className={`${styles['image-text_2']} flex-row justify-between`}>
                      <span className={`${styles['text-group_4']}`}>摄像头003</span>
                      <div className={`${styles['group_26']} flex-col`} />
                    </div>
                  </div>
                </div>
                <div className={`${styles['section_14']} flex-col`}>
                  <div className={`${styles['box_28']} flex-row`}>
                    <div className={`${styles['image-text_3']} flex-row justify-between`}>
                      <span className={`${styles['text-group_5']}`}>摄像头004</span>
                      <div className={`${styles['box_29']} flex-col`} />
                    </div>
                  </div>
                </div>
              </div>
              <div className={`${styles['block_9']} flex-col`} />
              <div className={`${styles['block_10']} flex-row`}>
                <div className={`${styles['box_30']} flex-col`} />
                <span className={`${styles['text_74']}`}>实时告警显示</span>
                <div className={`${styles['box_31']} flex-col`} />
              </div>
              <div className={`${styles['block_11']} flex-col justify-end`}>
                <div className={`${styles['box_32']} flex-row`}>
                  <div className={`${styles['list_1']} flex-row`}>
                    <div className={`${styles['list-items_1-0']} flex-col justify-end`}>
                      <div className={`${styles['text-wrapper_15-0']} flex-col`}>
                        <span className={`${styles['text_75-0']}`}>告警</span>
                      </div>
                      <div className={`${styles['block_12-0']} flex-col`}>
                        <div className={`${styles['text-group_6-0']} flex-col justify-between`}>
                          <span className={`${styles['text_76-0']}`}>打架斗殴</span>
                          <span className={`${styles['text_77-0']}`}>2023-02-20&nbsp;&nbsp;08:47:51</span>
                        </div>
                      </div>
                    </div>
                    <div className={`${styles['list-items_1-1']} flex-col justify-end`}>
                      <div className={`${styles['text-wrapper_15-1']} flex-col`}>
                        <span className={`${styles['text_75-1']}`}>预警</span>
                      </div>
                      <div className={`${styles['block_12-1']} flex-col`}>
                        <div className={`${styles['text-group_6-1']} flex-col justify-between`}>
                          <span className={`${styles['text_76-1']}`}>打架斗殴</span>
                          <span className={`${styles['text_77-1']}`}>2023-02-20&nbsp;&nbsp;08:47:51</span>
                        </div>
                      </div>
                    </div>
                    <div className={`${styles['list-items_1-2']} flex-col justify-end`}>
                      <div className={`${styles['text-wrapper_15-2']} flex-col`}>
                        <span className={`${styles['text_75-2']}`}>告警</span>
                      </div>
                      <div className={`${styles['block_12-2']} flex-col`}>
                        <div className={`${styles['text-group_6-2']} flex-col justify-between`}>
                          <span className={`${styles['text_76-2']}`}>打架斗殴</span>
                          <span className={`${styles['text_77-2']}`}>2023-02-20&nbsp;&nbsp;08:47:51</span>
                        </div>
                      </div>
                    </div>
                    <div className={`${styles['list-items_1-3']} flex-col justify-end`}>
                      <div className={`${styles['text-wrapper_15-3']} flex-col`}>
                        <span className={`${styles['text_75-3']}`}>告警</span>
                      </div>
                      <div className={`${styles['block_12-3']} flex-col`}>
                        <div className={`${styles['text-group_6-3']} flex-col justify-between`}>
                          <span className={`${styles['text_76-3']}`}>打架斗殴</span>
                          <span className={`${styles['text_77-3']}`}>2023-02-20&nbsp;&nbsp;08:47:51</span>
                        </div>
                      </div>
                    </div>
                    <div className={`${styles['list-items_1-4']} flex-col justify-end`}>
                      <div className={`${styles['text-wrapper_15-4']} flex-col`}>
                        <span className={`${styles['text_75-4']}`}>预警</span>
                      </div>
                      <div className={`${styles['block_12-4']} flex-col`}>
                        <div className={`${styles['text-group_6-4']} flex-col justify-between`}>
                          <span className={`${styles['text_76-4']}`}>打架斗殴</span>
                          <span className={`${styles['text_77-4']}`}>2023-02-20&nbsp;&nbsp;08:47:51</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className={`${styles['box_33']} flex-row`}>
                  <div className={`${styles['group_27']} flex-col`} />
                </div>
              </div>
            </div>
            <div className={`${styles['box_34']} flex-col`}>
              <div className={`${styles['section_15']} flex-col`} />
              <div className={`${styles['section_16']} flex-row`}>
                <div className={`${styles['section_17']} flex-col`} />
                <span className={`${styles['text_78']}`}>火眼金睛大模型</span>
                <div className={`${styles['section_18']} flex-col`} />
              </div>
              <div className={`${styles['section_19']} flex-col justify-end`}>
                <div className={`${styles['section_20']} flex-row justify-between`}>
                  <img
                    className={`${styles['label_1']}`}
                    src={
                      require('./assets/img/SketchPngbad65e8be9e7f404648cc03005a9eee86ccfe3bb1ab3a569856b8f9636196c0f.png')
                    }
                  />
                  <div className={`${styles['text-wrapper_16']} flex-col`}>
                    <span className={`${styles['text_79']}`}>欢迎使用火眼金睛大模型</span>
                  </div>
                </div>
                <div className={`${styles['section_21']} flex-row`}>
                  <div className={`${styles['group_28']} flex-col`} />
                </div>
                <div className={`${styles['section_22']} flex-row justify-between`}>
                  <div className={`${styles['text-wrapper_17']} flex-col`}>
                    <span className={`${styles['text_80']}`}>帮我找这个人</span>
                  </div>
                  <img
                    className={`${styles['label_2']}`}
                    src={
                      require('./assets/img/SketchPngb6d44331bb45449c8546fdf36e6ea19f8712368c3e2449dff0658fd33acc6e79.png')
                    }
                  />
                </div>
                <div className={`${styles['section_23']} flex-row justify-between`}>
                  <img
                    className={`${styles['label_3']}`}
                    src={
                      require('./assets/img/SketchPngbad65e8be9e7f404648cc03005a9eee86ccfe3bb1ab3a569856b8f9636196c0f.png')
                    }
                  />
                  <div className={`${styles['text-wrapper_18']} flex-col`}>
                    <span className={`${styles['text_81']}`}>ReID算法已启动，正在查找，分析结果见下方</span>
                  </div>
                </div>
                <div className={`${styles['section_24']} flex-row`}>
                  <div className={`${styles['section_25']} flex-col`}>
                    <img
                      className={`${styles['image_15']}`}
                      src={
                        require('./assets/img/SketchPng86869c65e3a023b2c0fcc0d6816b39285fc34c1a97323a7f989a1ac5b15d4a3a.png')
                      }
                    />
                    <div className={`${styles['group_29']} flex-row`}>
                      <div className={`${styles['group_30']} flex-col`} />
                      <span className={`${styles['text_82']}`}>出现频率</span>
                      <div className={`${styles['group_31']} flex-col`} />
                      <span className={`${styles['text_83']}`}>文本总结</span>
                    </div>
                    <div className={`${styles['group_32']} flex-row`}>
                      <div className={`${styles['text-wrapper_19']} flex-col`}>
                        <span className={`${styles['text_84']}`}>10</span>
                        <span className={`${styles['text_85']}`}>8</span>
                        <span className={`${styles['text_86']}`}>6</span>
                        <span className={`${styles['text_87']}`}>4</span>
                        <span className={`${styles['text_88']}`}>2</span>
                      </div>
                      <div className={`${styles['image-wrapper_4']} flex-col`}>
                        <img
                          className={`${styles['image_16']}`}
                          src={
                            require('./assets/img/SketchPngfcc0a04da0a7364e4b0879b1bc024af390eec42926c23aee3045672deaa7ae6f.png')
                          }
                        />
                        <img
                          className={`${styles['image_17']}`}
                          src={
                            require('./assets/img/SketchPng113d8a19dcd4ac97f33ce2e652a2630fe72bb571dc246ca3aafaa1b890af0d31.png')
                          }
                        />
                        <img
                          className={`${styles['image_18']}`}
                          src={
                            require('./assets/img/SketchPngb49cd0203d1ce878ad85b85f5ba6f922e1dd0fd0f5c1e59c03d42e609c4033cc.png')
                          }
                        />
                        <img
                          className={`${styles['image_19']}`}
                          src={
                            require('./assets/img/SketchPng445de3f6d38e21a76abd41f95b5bff8f76678980f6fa98bc6c178642e46aa6b9.png')
                          }
                        />
                        <img
                          className={`${styles['image_20']}`}
                          src={
                            require('./assets/img/SketchPng5bb4d54d2530bef1ba587f2166a039d3a94b3d83006e2d971f1aa9553085901b.png')
                          }
                        />
                      </div>
                      <span className={`${styles['paragraph_1']}`}>
                        目标任务今日共出现3次。最近一次时间：2015-12-25&nbsp;10:45:12&nbsp;&nbsp;
                        <br />
                        地点：东门摄像头
                      </span>
                    </div>
                    <div className={`${styles['group_33']} flex-row`}>
                      <span className={`${styles['text_89']}`}>0</span>
                      <div className={`${styles['group_34']} flex-col justify-between`}>
                        <img
                          className={`${styles['thumbnail_8']}`}
                          src={
                            require('./assets/img/SketchPngf47d7dbb1009428e856797b88b37413e735c941a0b6b2b2c2223bd05097454a6.png')
                          }
                        />
                        <span className={`${styles['text_90']}`}>东门</span>
                      </div>
                      <div className={`${styles['group_35']} flex-col justify-between`}>
                        <img
                          className={`${styles['thumbnail_9']}`}
                          src={
                            require('./assets/img/SketchPngbde09763c207e27347ec15645bcccb17d5b9aadbcfe27ca50b2f01d7fdd0c902.png')
                          }
                        />
                        <span className={`${styles['text_91']}`}>西门</span>
                      </div>
                    </div>
                    <div className={`${styles['image-text_4']} flex-row justify-between`}>
                      <div className={`${styles['box_35']} flex-col`} />
                      <span className={`${styles['text-group_7']}`}>关键帧缩略图</span>
                    </div>
                    <div className={`${styles['group_36']} flex-row`}>
                      <div className={`${styles['image-text_5']} flex-col justify-between`}>
                        <div className={`${styles['section_26']} flex-col`} />
                        <span className={`${styles['text-group_8']}`}>09:10:05&nbsp;摄像头1</span>
                      </div>
                      <div className={`${styles['image-text_6']} flex-col justify-between`}>
                        <div className={`${styles['section_27']} flex-col`} />
                        <span className={`${styles['text-group_9']}`}>09:10:05&nbsp;摄像头2</span>
                      </div>
                      <div className={`${styles['image-text_7']} flex-col justify-between`}>
                        <div className={`${styles['group_37']} flex-col`} />
                        <span className={`${styles['text-group_10']}`}>09:10:05&nbsp;摄像头3</span>
                      </div>
                    </div>
                    <img
                      className={`${styles['image_21']}`}
                      src={
                        require('./assets/img/SketchPng158905eb7581f2d216abfbbabb75f8d5a1c3b24fdb022e1627fdc57ac782219d.png')
                      }
                    />
                    <img
                      className={`${styles['image_22']}`}
                      src={
                        require('./assets/img/SketchPng45cefe7cf543a72b02d95d3bac19cbbaf8aaa940212b7ee18ef131fa6b86bbb2.png')
                      }
                    />
                    <img
                      className={`${styles['image_23']}`}
                      src={
                        require('./assets/img/SketchPngaf21f17680ea2f3865e0c02b92e2a618102f0dd0fca1372382c1cec5f597366b.png')
                      }
                    />
                    <span className={`${styles['text_92']}`}>人员查找报告：张嘉豪</span>
                  </div>
                </div>
                <div className={`${styles['section_28']} flex-row`}>
                  <div className={`${styles['group_38']} flex-row`}>
                    <span className={`${styles['text_93']}`}>请输入指令或语言</span>
                    <img
                      className={`${styles['label_4']}`}
                      src={
                        require('./assets/img/SketchPnge8fa8a0b5bde953f6cf595581b38e20e2cdcb2afc8e6e3b2eb2048c703b7efc7.png')
                      }
                    />
                    <img
                      className={`${styles['label_5']}`}
                      src={
                        require('./assets/img/SketchPng4a04466ab02f8a1707c95728107ce5bf60392d574ce8234effc469039fd102b6.png')
                      }
                    />
                    <div className={`${styles['block_13']} flex-col`} />
                  </div>
                </div>
                <div className={`${styles['section_29']} flex-row`}>
                  <div className={`${styles['box_36']} flex-col`} />
                </div>
              </div>
            </div>
          </div>
          <div className={`${styles['section_30']} flex-col`}>
            <div className={`${styles['block_14']} flex-col`}>
              <div className={`${styles['group_39']} flex-row`}>
                <div className={`${styles['box_37']} flex-col`} />
                <div className={`${styles['box_38']} flex-col`}>
                  <div className={`${styles['box_39']} flex-col`}>
                    <div className={`${styles['group_40']} flex-col`} />
                  </div>
                  <span className={`${styles['text_94']}`}>慧心极目·火眼金睛视频监控平台</span>
                </div>
                <div className={`${styles['box_40']} flex-col`} />
              </div>
            </div>
          </div>
          <div className={`${styles['section_31']} flex-col`}>
            <div className={`${styles['block_15']} flex-col`}>
              <div className={`${styles['image-wrapper_5']} flex-col`}>
                <img
                  className={`${styles['image_24']}`}
                  src={
                    require('./assets/img/SketchPng1bb1812365361c203f570c97d90c0b69e86746ba7f9f9be15e9dd92ca0acc192.png')
                  }
                />
              </div>
              <span className={`${styles['text_95']}`}>105</span>
              <span className={`${styles['text_96']}`}>异常次数</span>
              <img
                className={`${styles['image_25']}`}
                src={
                  require('./assets/img/SketchPng7dc10bb5477297dd5461265f0c49cb1e6f96cf1c5f3148649bfa4adff3f3ca14.png')
                }
              />
            </div>
            <img
              className={`${styles['image_26']}`}
              src={
                require('./assets/img/SketchPnge1c0f98a8c57ad967c3aef5b900e47d68f5aa3b7264eb686201afa0115f7495f.png')
              }
            />
          </div>
        </div>
      </div>
    );
  }
}
export default DDS_lanhupage_0;
