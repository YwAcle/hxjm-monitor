<template>
  <div class="monitor-container">
    <div class="main-content">
      <!-- 左侧面板 -->
      <div class="left-panel">
        <!-- 监控统计 -->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">监控统计</span>
          </div>
          <div class="panel-content basic-stats">
            <!-- 左侧数据 -->
            <div class="stats-left">
              <div class="total-devices">
                <div class="left-content">
                  <div class="device-icon"></div>
                  <div class="device-label">设备总数</div>
                </div>
                <div class="device-count">8<span class="unit">台</span></div>
              </div>
              <!-- 事件总数和设备事件 -->
              <div class="count-bottom">
                <div class="count-item">
                  <div class="value-info">42<span class="unit">次</span></div>
                  <div class="label">事件总数</div>
                </div>
                <div class="count-item">
                  <div class="value-unusual">3<span class="unit">次</span></div>
                  <div class="label">异常事件</div>
                </div>

              </div>
              <!-- 底部三个数据 -->
              <div class="count-bottom">
                <div class="count-item">
                  <div class="value-warn">5<span class="unit">次</span></div>
                  <div class="label">预警</div>
                </div>
                <div class="count-item">
                  <div class="value-danger">3<span class="unit">个</span></div>
                  <div class="label">报警</div>
                </div>
                <div class="count-item">
                  <div class="value-success">3<span class="unit">个</span></div>
                  <div class="label">已处理</div>
                </div>
              </div>
            </div>

            <!-- 右侧设备类型统计 -->
            <div class="stats-right">
              <div class="pie-chart"
                   ref="devicePieChart"></div>
            </div>
          </div>
        </div>

        <!-- 人流量监测-->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">人流量监测</span>
          </div>
          <div class="panel-content">
            <div class="flow-chart"
                 ref="flowChart"></div>
          </div>
        </div>

        <!-- 异常事件监测 -->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">人员识别</span>
          </div>
          <div class="panel-content">
            <personnel-records />
          </div>
        </div>
      </div>

      <!-- 中间区域 -->
      <div class="center-panel">
        <!-- 添加标题 -->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">实时监控</span>
          </div>
          <div class="panel-content">
            <el-carousel :interval="5000"
                         arrow="hover"
                         height="100%"
                         indicator-position="none">
              <el-carousel-item>
                <div class="video-grid"
                     :class="{ 'single-video': isSingleVideo }">
                  <div class="video-item"
                       v-for="(url, index) in videoUrls"
                       :key="index">
                    <VideoPlayer :index="index + 1"
                                 :videoUrl="url"
                                 streamType="flv" />
                  </div>
                </div>
              </el-carousel-item>
            </el-carousel>
          </div>
        </div>

        <!-- 下部分 -->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">监控算法</span>
          </div>
          <div class="panel-content">
            <!-- <div class="panel-content">
              <el-table :data="currentTableData"
                        style="width: 100%"
                        height="100%">
                <el-table-column prop="startTime"
                                 label="开始时间"
                                 width="100">
                </el-table-column>
                <el-table-column prop="name"
                                 label="事件名称"
                                 width="120">
                </el-table-column>
                <el-table-column prop="area"
                                 label="区域"
                                 width="100">
                </el-table-column>
                <el-table-column prop="description"
                                 label="报警描述"
                                 min-width="200">
                </el-table-column>
              </el-table>
            </div> -->
          </div>
        </div>
      </div>

      <!-- 右侧面板 -->
      <div class="right-panel">
        <!-- 频发事件统计 -->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">频发事件统计</span>
          </div>
          <div class="panel-content">
            <div class="rank-chart"
                 ref="rankChart"></div>
          </div>
        </div>

        <!-- 报警监测 -->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">报警统计</span>
          </div>
          <div class="panel-content">
            <div class="event-chart"
                 ref="eventChart"></div>

          </div>
        </div>

        <!-- 实时报警 -->
        <div class="panel-box">
          <div class="panel-header">
            <i class="panel-icon"></i>
            <span class="title">实时报警</span>
          </div>
          <div class="panel-content">
            <div class="alarm-chart"
                 ref="alarmChart"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加图片预览组件 -->
    <div class="image-preview"
         v-show="showPreview"
         @click="closePreview">
      <img :src="previewImage"
           alt="preview"
           @click.stop>
      <div class="close-btn"
           @click="closePreview">×</div>
    </div>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import VideoPlayer from './components/VideoPlayer.vue'
import PersonnelRecords from './components/PersonnelRecords.vue'
import { countTodayFlow } from '@/api/algdeployment/face_recognition_events'
export default {
  name: 'RealTimeMonitor',
  components: {
    VideoPlayer,
    PersonnelRecords
  },
  data () {
    return {
      devicePieChart: null,
      deviceData: [
        { value: 3, name: '海康威视V50' },
        { value: 3, name: 'TCL-A2000' },
        { value: 1, name: 'TCL-A1000' },
        { value: 1, name: '360云端摄像头' }
      ],
      flowChart: null,
      flowData: {
        times: [],
        values: []
      },
      flowTimer: null,
      eventChart: null,
      eventData: [
        ['08:00', 0, 5], ['09:00', 1, 3], ['10:00', 2, 8],
        ['11:00', 0, 2], ['12:00', 1, 4], ['13:00', 2, 6],
        ['14:00', 0, 3], ['15:00', 1, 7], ['16:00', 2, 4],
        ['17:00', 0, 5]
      ],
      areaNames: ['监控区', '出入口', '公共区'],
      rankChart: null,
      rankData: [
        { name: '周界入侵', value: 12 },
        { name: '陌生人预警', value: 1 },
        { name: '重点人员', value: 19 },
        { name: '火灾预警', value: 1 },
        { name: '防护预警', value: 1 },
        { name: 'ReID', value: 8 },
      ],
      alarmChart: null,
      alarmData: [
        {
          name: '人员入侵',
          area: 'A区域',
          time: '10:24',
          duration: 15,
          image: 'alarm1.jpg'
        },
        {
          name: '异常聚集',
          area: 'B区域',
          time: '11:30',
          duration: 25,
          image: 'alarm2.jpg'
        },
        {
          name: '可疑人员',
          area: 'C区域',
          time: '12:17',
          duration: 10,
          image: 'alarm3.jpg'
        },
        {
          name: '区域入侵',
          area: 'A区域',
          time: '14:20',
          duration: 30,
          image: 'alarm4.jpg'
        },
        {
          name: '人员追踪',
          area: 'B区域',
          time: '15:10',
          duration: 20,
          image: 'alarm5.jpg'
        }
      ],
      showPreview: false,
      previewImage: '',
      alarmTableData: [
        {
          startTime: '10:24:35',
          name: '人员入侵',
          area: 'A区域',
          description: '检测到未授权人员进入警戒区域'
        },
        {
          startTime: '11:30:22',
          name: '异常聚集',
          area: 'B区域',
          description: '检测到人员密度超过预警阈值'
        },
        {
          startTime: '12:17:45',
          name: '可疑人员',
          area: 'C区域',
          description: '发现疑似黑名单人员'
        },
        {
          startTime: '14:20:15',
          name: '区域入侵',
          area: 'A区域',
          description: '检测到非法闯入行为'
        },
        {
          startTime: '15:10:55',
          name: '人员追踪',
          area: 'B区域',
          description: '目标人员移动轨迹异常'
        }
      ],
      tableScrollTimer: null,
      currentTableData: [],
      tablePageSize: 4,
      videoUrls: [

        'http://192.168.108.238:82/live.flv?app=live&stream=13'
      ]
    }
  },
  computed: {
    isSingleVideo () {
      return this.videoUrls.length === 1
    }
  },
  mounted () {
    this.initDevicePieChart()
    this.initFlowChart()
    this.initEventChart()
    this.initRankChart()
    this.initAlarmChart()
    this.getFlowData()
    this.$nextTick(() => {
      this.startTableScroll()
    })
    this.flowTimer = setInterval(() => {
      this.getFlowData()
    }, 5 * 60 * 1000)
  },
  beforeDestroy () {
    if (this.devicePieChart) {
      this.devicePieChart.dispose()
    }
    if (this.flowChart) {
      this.flowChart.dispose()
    }
    if (this.eventChart) {
      this.eventChart.dispose()
    }
    if (this.rankChart) {
      this.rankChart.dispose()
    }
    if (this.rankInterval) {
      clearInterval(this.rankInterval)
    }
    if (this.alarmChart) {
      this.alarmChart.dispose()
    }
    this.stopTableScroll()
    if (this.flowTimer) {
      clearInterval(this.flowTimer)
    }
  },
  methods: {
    vw (px) {
      return (px / 1920) * window.innerWidth
    },

    vh (px) {
      return (px / 1080) * window.innerHeight
    },

    initDevicePieChart () {
      this.devicePieChart = echarts.init(this.$refs.devicePieChart)

      const option = {
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'item',
          formatter: '{b}: {c}台 ({d}%)',
          backgroundColor: 'rgba(0,40,85,0.8)',
          borderColor: 'rgba(0,149,255,0.2)',
          textStyle: {
            color: '#fff'
          }
        },
        legend: {
          orient: 'vertical',
          top: 'center',
          right: '0%',
          textStyle: {
            color: 'rgba(255,255,255,0.85)',
            fontSize: 14
          },
          itemWidth: 10,
          itemHeight: 10,
          itemGap: 20
        },
        series: [
          {
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['35%', '50%'],
            avoidLabelOverlap: false,
            itemStyle: {
              borderRadius: 4,
              borderColor: 'rgba(0,40,85,0.8)',
              borderWidth: 2
            },
            label: {
              show: true,
              position: 'inside',
              formatter: '{c}台',
              fontSize: 14,
              color: '#fff',
              textShadow: '0 0 3px rgba(0,0,0,0.3)',
              fontWeight: 'bold'
            },
            labelLine: {
              show: false
            },
            emphasis: {
              label: {
                show: true,
                fontSize: 16,
                fontWeight: 'bold'
              },
              itemStyle: {
                shadowBlur: 10,
                shadowOffsetX: 0,
                shadowColor: 'rgba(0,149,255,0.5)'
              }
            },
            data: this.deviceData.map(item => ({
              ...item,
              itemStyle: {
                color: this.getItemColor(item.name)
              }
            }))
          }
        ]
      }

      this.devicePieChart.setOption(option)

      // 添加窗口大小变化的监听
      window.addEventListener('resize', this.resizeChart)
    },

    resizeChart () {
      if (this.devicePieChart) {
        this.devicePieChart.resize()
      }
    },

    // 获取不同类型的颜色
    getItemColor (name) {
      const colors = {
        'ReID': new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#00bfff' },
          { offset: 1, color: '#0080ff' }
        ]),
        '人脸超分': new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#00ff7f' },
          { offset: 1, color: '#00bf60' }
        ]),
        '异常检测': new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#ffd700' },
          { offset: 1, color: '#ffa500' }
        ])
      }
      return colors[name]
    },

    initFlowChart () {
      this.flowChart = echarts.init(this.$refs.flowChart)

      const option = {
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(0,40,85,0.9)',
          borderColor: 'rgba(0,149,255,0.3)',
          borderWidth: 1,
          padding: [10, 15],
          textStyle: {
            color: '#fff',
            fontSize: 13
          },
          formatter: (params) => {
            const data = params[0];
            return `
              <div style="font-weight:500">
                ${data.name}<br/>
                人流量：${data.value} 人次
              </div>
            `;
          }
        },
        grid: {
          top: this.vh(25),
          left: this.vw(25),
          right: this.vw(20),
          bottom: this.vh(25),
          containLabel: true
        },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: this.flowData.times,
          axisLine: {
            lineStyle: {
              color: 'rgba(255,255,255,0.2)'
            }
          },
          axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11,
            margin: 8
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: 'rgba(255,255,255,0.05)',
              type: 'dashed'
            }
          }
        },
        yAxis: {
          type: 'value',
          name: '人次',
          nameTextStyle: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11,
            padding: [0, 20, 0, 0]
          },
          splitLine: {
            lineStyle: {
              color: 'rgba(255,255,255,0.05)',
              type: 'dashed'
            }
          },
          axisLine: {
            show: false
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11,
            margin: 8
          }
        },
        series: [
          {
            name: '人流量',
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 8,
            showSymbol: true,
            lineStyle: {
              width: 3,
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#00bfff' },
                { offset: 1, color: '#0080ff' }
              ])
            },
            itemStyle: {
              color: '#00bfff',
              borderColor: '#fff',
              borderWidth: 2,
              shadowColor: 'rgba(0,191,255,0.5)',
              shadowBlur: 10
            },
            areaStyle: {
              opacity: 0.3,
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(0,191,255,0.5)' },
                { offset: 0.5, color: 'rgba(0,191,255,0.15)' },
                { offset: 1, color: 'rgba(0,191,255,0.05)' }
              ])
            },
            emphasis: {
              scale: true,
              focus: 'series',
              itemStyle: {
                borderWidth: 3
              }
            },
            data: this.flowData.values,
            markPoint: {
              symbol: 'circle',
              symbolSize: 50,
              itemStyle: {
                color: 'rgba(0,191,255,0.2)'
              },
              data: [
                { type: 'max', name: '最大值', label: { fontSize: 12 } },
                { type: 'min', name: '最小值', label: { fontSize: 12 } }
              ]
            },
            markLine: {
              silent: true,
              lineStyle: {
                color: 'rgba(255,255,255,0.2)',
                type: 'dashed'
              },
              data: [
                { type: 'average', name: '平均值' }
              ]
            }
          }
        ]
      }

      this.flowChart.setOption(option)
      window.addEventListener('resize', this.resizeFlowChart)
    },

    resizeFlowChart () {
      if (this.flowChart) {
        this.flowChart.resize()
      }
    },

    initEventChart () {
      this.eventChart = echarts.init(this.$refs.eventChart)

      const option = {
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(0,40,85,0.9)',
          borderColor: 'rgba(0,149,255,0.3)',
          borderWidth: 1,
          padding: [10, 15],
          formatter: (params) => {
            return `
              <div style="font-weight:500;padding:2px 8px;">
                <span style="color:#00bfff">${this.areaNames[params.value[1]]}</span><br/>
                <span style="color:rgba(255,255,255,0.8)">时间：${params.value[0]}</span><br/>
                <span style="color:#ffd700">异常次数：${params.value[2]}次</span>
              </div>
            `
          }
        },
        grid: {
          top: this.vh(25),
          left: this.vw(5),
          right: this.vw(20),
          bottom: this.vh(40),
          containLabel: true
        },
        xAxis: {
          type: 'category',
          data: this.flowData.times,
          nameTextStyle: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11,
            padding: [15, 0, 0, 0]
          },
          axisLine: {
            lineStyle: {
              color: 'rgba(255,255,255,0.2)'
            }
          },
          axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11,
            margin: 8
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: 'rgba(255,255,255,0.05)',
              type: 'dashed'
            }
          }
        },
        yAxis: {
          type: 'category',
          name: '区域',
          nameTextStyle: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11,
            padding: [0, 20, 0, 0]
          },
          data: this.areaNames,
          axisLine: {
            lineStyle: {
              color: 'rgba(255,255,255,0.2)'
            }
          },
          axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11,
            margin: 8
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: 'rgba(255,255,255,0.05)',
              type: 'dashed'
            }
          }
        },
        visualMap: {
          min: 0,
          max: 10,
          calculable: true,
          orient: 'horizontal',
          left: 'center',
          bottom: this.vh(10),
          dimension: 2,
          itemWidth: this.vw(20),
          itemHeight: this.vh(25),
          text: ['异常频次(高)', '异常频次(低)'],
          textStyle: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 11
          },
          inRange: {
            symbolSize: [15, 50],
            color: [
              'rgba(0,191,255,0.3)',
              'rgba(255,215,0,0.5)',
              'rgba(255,77,79,0.8)'
            ]
          },
          textGap: 10,
          showLabel: true,
          seriesIndex: [0],
          pieces: [
            { value: 0, color: 'rgba(0,191,255,0.3)' },
            { min: 1, max: 3, color: 'rgba(0,191,255,0.5)' },
            { min: 4, max: 6, color: 'rgba(255,215,0,0.5)' },
            { min: 7, color: 'rgba(255,77,79,0.8)' }
          ]
        },
        series: [
          {
            name: '异常事件',
            type: 'scatter',
            data: this.eventData,
            symbol: 'circle',
            itemStyle: {
              borderColor: '#fff',
              borderWidth: 2,
              shadowColor: 'rgba(0,191,255,0.5)',
              shadowBlur: 10
            },
            emphasis: {
              itemStyle: {
                borderWidth: 3,
                shadowBlur: 20,
                shadowColor: 'rgba(255,255,255,0.5)'
              },
              scale: true
            },
            markLine: {
              silent: true,
              lineStyle: {
                color: 'rgba(255,255,255,0.2)',
                type: 'dashed'
              },
              data: [
                {
                  type: 'average',
                  name: '平均值',
                  label: {
                    color: 'rgba(255,255,255,0.7)',
                    fontSize: 12
                  }
                }
              ]
            }
          }
        ],
        animation: true,
        animationDuration: 1500,
        animationEasing: 'cubicInOut'
      }

      this.eventChart.setOption(option)
      window.addEventListener('resize', this.resizeEventChart)
    },

    resizeEventChart () {
      if (this.eventChart) {
        this.eventChart.resize()
      }
    },

    initRankChart () {
      this.rankChart = echarts.init(this.$refs.rankChart)

      const sortedData = [...this.rankData]
        .sort((a, b) => b.value - a.value)
        .slice(0, 5)
        .reverse()

      const option = {
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          },
          formatter: (params) => {
            const data = params[0]
            return `
              <div style="padding: 3px 6px">
                <span style="color:#00bfff;font-weight:500">${data.name}</span><br/>
                <span style="color:rgba(255,255,255,0.8)">发生次数：${data.value}次</span>
              </div>
            `
          },
          backgroundColor: 'rgba(0,40,85,0.9)',
          borderColor: 'rgba(0,149,255,0.3)',
          borderWidth: 1,
          padding: [8, 12],
          textStyle: {
            fontSize: 13
          }
        },
        grid: {
          top: '3%',
          left: '0%',
          right: '6%',
          bottom: '3%',
          containLabel: true
        },
        xAxis: {
          type: 'value',
          show: false
        },
        yAxis: {
          type: 'category',
          data: sortedData.map(item => item.name),
          axisLine: {
            show: false
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            color: 'rgba(255,255,255,0.9)',
            fontSize: 13,
            margin: 16,
            formatter: (value) => {
              if (value.length > 10) {
                return value.substring(0, 10) + '...'
              }
              return value
            }
          }
        },
        series: [
          {
            type: 'bar',
            data: sortedData.map(item => ({
              value: item.value,
              itemStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                  { offset: 0, color: 'rgba(0,191,255,0.2)' },
                  { offset: 1, color: 'rgba(0,191,255,0.8)' }
                ]),
                borderRadius: [0, 4, 4, 0]
              }
            })),
            barWidth: '30%',
            label: {
              show: true,
              position: 'right',
              color: '#00bfff',
              fontSize: 14,
              fontWeight: 500,
              formatter: '{c}次',
              distance: 10,
              textShadow: '0 0 10px rgba(0,191,255,0.4)'
            }
          }
        ],
        animationDuration: 1000,
        animationEasing: 'cubicInOut'
      }

      this.rankChart.setOption(option)

      // 修改轮播逻辑
      let currentIndex = 0
      const allData = [...this.rankData].sort((a, b) => b.value - a.value)

      this.rankInterval = setInterval(() => {
        currentIndex = (currentIndex + 1) % allData.length

        // 获取要显示的5条数据
        let displayData = []
        for (let i = 0; i < 5; i++) {
          const index = (currentIndex + i) % allData.length
          displayData.push(allData[index])
        }

        // 反转数组使大的在上方
        displayData = displayData.reverse()

        this.rankChart.setOption({
          yAxis: {
            data: displayData.map(item => item.name)
          },
          series: [{
            data: displayData.map(item => ({
              value: item.value,
              itemStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                  { offset: 0, color: 'rgba(0,191,255,0.2)' },
                  { offset: 1, color: 'rgba(0,191,255,0.8)' }
                ]),
                borderRadius: [0, 4, 4, 0]
              }
            }))
          }]
        })
      }, 3000)

      window.addEventListener('resize', this.resizeRankChart)
    },

    resizeRankChart () {
      if (this.rankChart) {
        this.rankChart.resize()
      }
    },

    initAlarmChart () {
      this.alarmChart = echarts.init(this.$refs.alarmChart)

      const option = {
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(0,40,85,0.95)',
          borderColor: 'rgba(0,149,255,0.3)',
          borderWidth: 1,
          padding: [10, 15],
          confine: true,
          enterable: true,
          hideDelay: 300,
          position: function (point, params, dom, rect, size) {
            const [x, y] = point
            const { contentSize, viewSize } = size
            const [width, height] = contentSize
            const [viewWidth, viewHeight] = viewSize

            let posX = x + 20
            let posY = y + 20

            if (posX + width > viewWidth) {
              posX = x - width - 20
            }

            if (posY + height > viewHeight) {
              posY = y - height - 20
            }

            return [posX, posY]
          },
          formatter: (params) => {
            const data = params[0].data
            return `
              <div style="padding:5px">
                <div style="font-size:14px;color:#00bfff;margin-bottom:8px">
                  ${data.name}
                </div>
                <div style="font-size:13px;color:rgba(255,255,255,0.9);margin-bottom:5px">
                  区域：${data.area}
                </div>
                <div style="font-size:13px;color:rgba(255,255,255,0.9);margin-bottom:5px">
                  时间：${data.time}
                </div>
                <div style="font-size:13px;color:rgba(255,255,255,0.9);margin-bottom:8px">
                  持续时长：${data.duration}分钟
                </div>
                <img
                  src="${data.image}"
                  style="width:160px;height:90px;object-fit:cover;border-radius:4px;border:1px solid rgba(0,149,255,0.3);cursor:pointer;transition:all 0.3s"
                  onmouseover="this.style.transform='scale(1.02)';this.style.boxShadow='0 0 10px rgba(0,149,255,0.3)'"
                  onmouseout="this.style.transform='scale(1)';this.style.boxShadow='none'"
                  onclick="document.querySelector('.monitor-container').__vue__.openPreview('${data.image}')"
                />
              </div>
            `
          }
        },
        grid: {
          top: '15%',
          left: '3%',
          right: '5%',
          bottom: '8%',
          containLabel: true
        },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: this.alarmData.map(item => item.time),
          axisLine: {
            lineStyle: {
              color: 'rgba(255,255,255,0.2)'
            }
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 12,
            margin: 12
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: 'rgba(255,255,255,0.05)',
              type: 'dashed'
            }
          }
        },
        yAxis: {
          type: 'value',
          name: '报警时长(分钟)',
          nameTextStyle: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 12,
            padding: [0, 30, 0, 0]
          },
          min: 0,
          max: function (value) {
            return Math.ceil(value.max / 10) * 10;
          },
          interval: 10,
          splitLine: {
            lineStyle: {
              color: 'rgba(255,255,255,0.05)',
              type: 'dashed'
            }
          },
          axisLine: {
            show: false
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 12
          }
        },
        series: [
          {
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 12,
            data: this.alarmData.map(item => ({
              name: item.name,
              value: item.duration,
              area: item.area,
              time: item.time,
              duration: item.duration,
              image: item.image
            })),
            lineStyle: {
              width: 3,
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#00bfff' },
                { offset: 1, color: '#0080ff' }
              ])
            },
            itemStyle: {
              color: '#ff4d4f',
              borderColor: '#fff',
              borderWidth: 2,
              shadowColor: 'rgba(255,77,79,0.5)',
              shadowBlur: 10
            },
            areaStyle: {
              opacity: 0.3,
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(0,191,255,0.5)' },
                { offset: 0.5, color: 'rgba(0,191,255,0.15)' },
                { offset: 1, color: 'rgba(0,191,255,0.05)' }
              ])
            },
            emphasis: {
              focus: 'series',
              scale: true,
              itemStyle: {
                color: '#ff4d4f',
                borderWidth: 3,
                shadowBlur: 20,
                shadowColor: 'rgba(255,77,79,0.8)'
              }
            }
          }
        ],
        animationDuration: 1000,
        animationEasing: 'cubicInOut'
      }

      this.alarmChart.setOption(option)
      window.addEventListener('resize', this.resizeAlarmChart)
    },

    resizeAlarmChart () {
      if (this.alarmChart) {
        this.alarmChart.resize()
      }
    },

    // 打开图片预览
    openPreview (image) {
      this.previewImage = image
      this.showPreview = true
    },

    // 关闭图片预览
    closePreview () {
      this.showPreview = false
      this.previewImage = ''
    },

    // 开始表格滚动
    startTableScroll () {
      // 先清除可能存在的定时器
      this.stopTableScroll()

      // 初始化显示前4条数据
      this.currentTableData = this.alarmTableData.slice(0, this.tablePageSize)

      let currentIndex = 0
      this.tableScrollTimer = setInterval(() => {
        currentIndex = (currentIndex + 1) % this.alarmTableData.length

        // 获取要显示的数据
        this.currentTableData = []
        for (let i = 0; i < this.tablePageSize; i++) {
          const index = (currentIndex + i) % this.alarmTableData.length
          this.currentTableData.push(this.alarmTableData[index])
        }
      }, 3000) // 每3秒轮播一次
    },

    // 停止表格滚动
    stopTableScroll () {
      if (this.tableScrollTimer) {
        clearInterval(this.tableScrollTimer)
        this.tableScrollTimer = null
      }
    },

    // 获取人流量数据
    async getFlowData () {
      try {
        const res = await countTodayFlow()
        if (res.code === 200) {
          // 处理数据
          this.flowData.times = res.data.map(item => item.hour + ':00')
          this.flowData.values = res.data.map(item => item.count)
          // 更新图表
          this.updateFlowChart()
        }
      } catch (error) {
        console.error('获取人流量数据失败:', error)
      }
    },

    // 更新人流量图表
    updateFlowChart () {
      if (!this.flowChart) return

      this.flowChart.setOption({
        xAxis: {
          data: this.flowData.times
        },
        series: [{
          data: this.flowData.values
        }]
      })
    }
  }
}
</script>

<style lang="scss" scoped>
// 添加视口单位转换函数
@function vw($px) {
  @return ($px / 1920) * 100vw;
}

@function vh($px) {
  @return ($px / 1080) * 100vh;
}

.monitor-container {
  width: 100%;
  height: 100%;
  padding: vh(10) vw(20);
  background: transparent;

  .main-content {
    height: 100%;
    display: flex;
    gap: vw(20);

    .left-panel,
    .right-panel {
      width: vw(540);
      display: flex;
      flex-direction: column;
      gap: vh(20);

      // 修改左右两侧面板的高度分配
      .panel-box {
        flex: 1; // 改为flex: 1确保等分
        display: flex;
        flex-direction: column;

        .panel-content {
          flex: 1;
          overflow: auto;
        }
      }
    }

    .center-panel {
      flex: 1;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: vh(20);

      .panel-box {
        display: flex;
        flex-direction: column;

        &:first-child {
          flex: 17; // 上面占2份
        }

        &:last-child {
          flex: 8; // 下面占1份
        }

        .panel-content {
          flex: 1;
          height: 100%;
        }
      }
    }
  }
}

// 面板样式
.panel-box {
  background: linear-gradient(rgba(0, 40, 85, 0.95), rgba(0, 60, 130, 0.95));
  border: 1px solid rgba(0, 149, 255, 0.3);
  border-radius: vw(4);
  transition: all 0.3s ease;
  box-shadow: 0 0 30px rgba(0, 149, 255, 0.1);

  &:hover {
    box-shadow: 0 0 40px rgba(0, 149, 255, 0.15);
  }

  .panel-header {
    height: vh(45);
    padding: 0 vw(20);
    display: flex;
    align-items: center;
    border-bottom: 1px solid rgba(0, 149, 255, 0.2);
    position: relative;
    background: linear-gradient(90deg, rgba(0, 149, 255, 0.1), transparent 50%);

    // 添加左侧发光装饰
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: vw(2);
      height: 60%;
      background: linear-gradient(to bottom, #00bfff, #0080ff);
      box-shadow: 0 0 15px rgba(0, 191, 255, 0.5);
    }

    // 添加底部渐变线
    &::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(
        90deg,
        rgba(0, 149, 255, 0.4),
        rgba(0, 149, 255, 0.1)
      );
    }

    .panel-icon {
      width: vw(4);
      height: vh(18);
      background: linear-gradient(to bottom, #00bfff, #0080ff);
      margin-right: vw(12);
      border-radius: vw(2);
      position: relative;

      // 添加图标发光效果
      &::after {
        content: '';
        position: absolute;
        inset: -1px;
        border-radius: inherit;
        background: inherit;
        filter: blur(2px);
        opacity: 0.5;
      }
    }

    .title {
      font-size: vw(16);
      color: #fff;
      text-shadow: 0 0 10px rgba(0, 149, 255, 0.5);
      letter-spacing: 1px;
      font-weight: 500;
      position: relative;
      padding-left: vw(2);

      // 添加标题悬停效果
      &:hover {
        text-shadow: 0 0 15px rgba(0, 149, 255, 0.8);
      }
    }
  }

  .panel-content {
    padding: vh(10) vw(10);
  }
}

// 滚动条样式
::-webkit-scrollbar {
  width: vw(4);
}

::-webkit-scrollbar-thumb {
  background: rgba(0, 149, 255, 0.2);
  border-radius: vw(2);
}

::-webkit-scrollbar-track {
  background: rgba(0, 40, 85, 0.3);
}

// 今日实况区域样式
.basic-stats {
  display: flex;
  gap: vw(20);
  height: 100%;
  position: relative;

  // 添加分割线
  &::after {
    content: '';
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translateY(-50%);
    width: 1px;
    height: 90%;
    background: linear-gradient(
      to bottom,
      transparent,
      rgba(0, 149, 255, 0.3) 20%,
      rgba(0, 149, 255, 0.3) 80%,
      transparent
    );
    box-shadow: 0 0 15px rgba(0, 149, 255, 0.2);
  }

  // 左侧数据
  .stats-left {
    flex: 1;
    padding-right: vw(20);
    display: flex;
    flex-direction: column;
    gap: vh(15);
    height: 100%;
    max-height: 100%;
    overflow: hidden;

    // 设备总数区域
    .total-devices {
      flex: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: vh(30);

      background: rgba(0, 40, 85, 0.3);
      border-radius: vw(4);
      border: 1px solid rgba(0, 149, 255, 0.2);

      // 左侧容器
      .left-content {
        display: flex;
        align-items: center;
        gap: vw(10);
      }

      .device-icon {
        width: vw(30);
        height: vw(30);
        background: url('../../assets/images/screen/icons/monitor.svg')
          no-repeat center;
        background-size: contain;
        opacity: 0.8;
        filter: invert(67%) sepia(72%) saturate(4079%) hue-rotate(177deg)
          brightness(102%) contrast(104%);
      }

      .device-label {
        font-size: vw(18);
        color: rgba(255, 255, 255);
      }

      .device-count {
        font-size: vw(28);
        color: #00bfff;
        text-shadow: 0 0 10px rgba(0, 149, 255, 0.4);

        .unit {
          font-size: vw(18);
          margin-left: vw(4);
          color: rgb(255, 255, 255);
        }
      }
    }

    // 底部统计区域
    .count-bottom {
      display: flex;
      justify-content: space-between;
      gap: vw(10);
      margin-top: auto;

      .count-item {
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: vh(10) vw(10);
        background: rgba(0, 40, 85, 0.3);
        border: 1px solid rgba(0, 149, 255, 0.2);
        border-radius: vw(4);
        transition: all 0.3s ease;
        position: relative;
        text-align: center;

        // 添加渐变背景效果
        &::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(
            135deg,
            transparent,
            rgba(0, 149, 255, 0.05)
          );
          pointer-events: none;
        }

        &:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0, 149, 255, 0.15);
          border-color: rgba(0, 149, 255, 0.4);

          &::after {
            background: linear-gradient(
              135deg,
              transparent,
              rgba(0, 149, 255, 0.1)
            );
          }
        }

        // 数值样式统一设置
        [class^='value-'] {
          position: relative;
          z-index: 1;
          font-size: vw(28);
          font-weight: 500;
          margin-bottom: vh(8);
          letter-spacing: 0.5px;

          .unit {
            font-size: vw(16);
            margin-left: vw(4);
            font-weight: normal;
            color: rgba(255, 255, 255);
            opacity: 0.9;
          }
        }

        .label {
          position: relative;
          z-index: 1;
          font-size: vw(12);
          color: rgba(255, 255, 255);
          letter-spacing: 1px;
        }

        // 不同状态的颜色和效果
        .value-info {
          color: #00bfff;
          text-shadow: 0 0 15px rgba(0, 191, 255, 0.4);
        }

        .value-unusual {
          color: #ffa500;
          text-shadow: 0 0 15px rgba(255, 165, 0, 0.4);
        }

        .value-warn {
          color: #ffd700;
          text-shadow: 0 0 15px rgba(255, 215, 0, 0.4);
        }

        .value-danger {
          color: #ff4d4f;
          text-shadow: 0 0 15px rgba(255, 77, 79, 0.4);
        }

        .value-success {
          color: #52c41a;
          text-shadow: 0 0 机15px rgba(82, 196, 26, 0.4);
        }
      }
    }
  }

  // 右侧设备类型统计
  .stats-right {
    flex: 1;
    overflow: auto;

    .pie-chart {
      width: 100%;
      height: 100%;
    }
  }
}

.flow-chart,
.event-chart {
  width: 100%;
  height: 100%;
  padding: vh(10) vw(10);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

// 添加排行榜样式
.panel-content {
  :deep(.dv-scroll-ranking-board) {
    width: 100%;
    height: 100%;
    padding: vh(10);

    .row-item {
      transition: all 0.3s;

      &:hover {
        background: rgba(0, 149, 255, 0.1) !important;
        transform: translateX(4px);
      }
    }

    .ranking-info {
      display: flex;
      align-items: center;
      gap: vw(10);

      .rank {
        min-width: vw(20);
        height: vw(20);
        line-height: vw(20);
        text-align: center;
        background: rgba(0, 149, 255, 0.2);
        border-radius: vw(2);
        color: #fff;
        font-size: vw(12);
      }

      .info-name {
        flex: 1;
      }
    }
  }
}

.rank-chart {
  width: 100%;
  height: 100%;
  padding: vh(5);
}

.alarm-chart {
  width: 100%;
  height: 100%;
  padding: vh(5);
}

.image-preview {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.3s ease;

  img {
    max-width: 90vw;
    max-height: 90vh;
    object-fit: contain;
    border-radius: 4px;
    box-shadow: 0 0 20px rgba(0, 149, 255, 0.3);
    animation: zoomIn 0.3s ease;
  }

  .close-btn {
    position: absolute;
    top: 20px;
    right: 20px;
    width: 40px;
    height: 40px;
    line-height: 40px;
    text-align: center;
    font-size: 24px;
    color: #fff;
    background: rgba(0, 40, 85, 0.8);
    border-radius: 50%;
    cursor: pointer;
    transition: all 0.3s;

    &:hover {
      background: rgba(0, 149, 255, 0.8);
      transform: rotate(90deg);
    }
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes zoomIn {
  from {
    transform: scale(0.9);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

// 将表格样式移到最外层
::v-deep .el-table {
  background-color: transparent !important;
  color: #fff;
  font-size: vw(13);

  // 去除默认边框
  &::before,
  &::after {
    display: none;
  }

  // 表头样式
  .el-table__header-wrapper {
    th {
      background-color: rgba(0, 40, 85, 0.8) !important;
      color: rgba(255, 255, 255, 0.9);
      font-weight: 500;
      border-bottom: 1px solid rgba(0, 149, 255, 0.3);
      padding: vw(8) 0;
      font-size: vw(13);

      .cell {
        word-break: break-all;
        line-height: vw(20);
      }
    }
  }

  // 表体样式
  .el-table__body-wrapper {
    background-color: transparent;

    tr {
      background-color: transparent;
      transition: all 0.3s;
      height: vw(40);

      &:hover > td {
        background-color: rgba(0, 149, 255, 0.1) !important;
      }

      td {
        background-color: transparent !important;
        border-bottom: 1px solid rgba(0, 149, 255, 0.1);
        padding: vw(10) vw(5);
        transition: all 0.3s;
        font-size: vw(13);

        // 时间列样式
        &:first-child .cell {
          color: rgba(255, 255, 255, 0.8);
          font-family: 'Courier New', monospace;
          font-size: vw(13);
        }

        // 事件名称列样式
        &:nth-child(2) .cell {
          color: #00bfff;
          font-weight: 500;
          font-size: vw(13);
        }

        // 区域列样式
        &:nth-child(3) .cell {
          color: #ffd700;
          font-size: vw(13);
        }

        // 描述列样式
        &:last-child .cell {
          color: rgba(255, 255, 255, 0.7);
          font-size: vw(13);
        }

        .cell {
          word-break: break-all;
          line-height: vw(20);
        }
      }
    }
  }

  // 滚动条样式
  .el-table__body-wrapper::-webkit-scrollbar {
    width: vw(6);
    background-color: transparent;
  }

  .el-table__body-wrapper::-webkit-scrollbar-thumb {
    background-color: rgba(0, 149, 255, 0.2);
    border-radius: vw(3);

    &:hover {
      background-color: rgba(0, 149, 255, 0.3);
    }
  }

  // 空数据样式
  .el-table__empty-block {
    background-color: transparent;

    .el-table__empty-text {
      color: rgba(255, 255, 255, 0.5);
      font-size: vw(13);
    }
  }
}

// 添加表格行高亮样式
::v-deep .el-table {
  .el-table__body-wrapper {
    tr {
      // ... 其他样式保持不变

      // 当前行高亮样式
      &.current-row > td {
        background-color: rgba(0, 149, 255, 0.15) !important;

        // 时间列样式
        &:first-child .cell {
          color: rgba(255, 255, 255, 0.95);
        }

        // 事件名称列样式
        &:nth-child(2) .cell {
          color: #1ac8ff;
        }

        // 区域列样式
        &:nth-child(3) .cell {
          color: #ffe666;
        }

        // 描述列样式
        &:last-child .cell {
          color: rgba(255, 255, 255, 0.9);
        }
      }
    }
  }
}

// 添加视频网格样式
.panel-content {
  height: 100%;
  background: rgba(0, 40, 85, 0.3);

  ::v-deep .el-carousel {
    height: 100%;

    .el-carousel__container {
      height: 100%;
    }

    .el-carousel__item {
      height: 100%;
    }
  }
}

.video-grid {
  width: 100%;
  height: 100%;
  padding: vh(10);

  &.single-video {
    .video-item {
      width: 100%;
      height: 100%;
    }
  }

  &:not(.single-video) {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: repeat(2, 1fr);
    gap: vh(10);
  }
}

.video-item {
  width: 100%;
  height: 100%;
  background: rgba(0, 40, 85, 0.5);
  border: 1px solid rgba(0, 149, 255, 0.3);
  border-radius: vw(4);
  overflow: hidden;
  position: relative;

  &:hover {
    border-color: rgba(0, 149, 255, 0.6);
    box-shadow: 0 0 15px rgba(0, 149, 255, 0.2);
  }
}
</style>

