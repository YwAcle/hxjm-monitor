<template>
  <div class="app-container">
    <el-form :model="queryParams"
             ref="queryForm"
             size="small"
             :inline="true"
             v-show="showSearch"
             class="search-form"
             label-width="68px">
      <el-form-item label="布控算法名称"
                    prop="algBkName">
        <el-input v-model="queryParams.algBkName"
                  placeholder="请输入布控算法名称"
                  clearable
                  @keyup.enter.native="handleQuery" />
      </el-form-item>
      <el-form-item label="布控算法类型"
                    prop="algBkType">
        <el-select v-model="queryParams.algBkType"
                   placeholder="请选择布控算法类型"
                   clearable>
          <el-option v-for="dict in dict.type.alg_bk_type"
                     :key="dict.value"
                     :label="dict.label"
                     :value="dict.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="启用标志"
                    prop="status">
        <el-select v-model="queryParams.status"
                   placeholder="请选择启用标志"
                   clearable>
          <el-option v-for="dict in dict.type.basedata_isvalid"
                     :key="dict.value"
                     :label="dict.label"
                     :value="dict.value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary"
                   icon="el-icon-search"
                   size="mini"
                   @click="handleQuery">搜索</el-button>
        <el-button icon="el-icon-refresh"
                   size="mini"
                   @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10"
            class="table-toolbar mb8">
      <el-col :span="1.5">
        <el-button type="primary"
                   plain
                   icon="el-icon-plus"
                   size="mini"
                   @click="handleAdd"
                   v-hasPermi="['algdeployment:algdeploymentmanagement:add']">新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success"
                   plain
                   icon="el-icon-edit"
                   size="mini"
                   :disabled="single"
                   @click="handleUpdate"
                   v-hasPermi="['algdeployment:algdeploymentmanagement:edit']">修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger"
                   plain
                   icon="el-icon-delete"
                   size="mini"
                   :disabled="multiple"
                   @click="handleBatchDelete"
                   v-hasPermi="['algdeployment:algdeploymentmanagement:remove']">删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning"
                   plain
                   icon="el-icon-download"
                   size="mini"
                   @click="handleExport"
                   v-hasPermi="['algdeployment:algdeploymentmanagement:export']">导出</el-button>
      </el-col>
      <right-toolbar :showSearch.sync="showSearch"
                     @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading"
              :data="algdeploymentmanagementList"
              class="main-table"
              @selection-change="handleSelectionChange">
      <el-table-column type="selection"
                       width="55"
                       align="center" />
      <el-table-column label="主键"
                       align="center"
                       prop="id" />
      <el-table-column label="布控算法名称"
                       align="center"
                       prop="algBkName" />
      <el-table-column label="布控算法类型"
                       align="center"
                       prop="algBkType">
        <template slot-scope="scope">
          <dict-tag :options="dict.type.alg_bk_type"
                    :value="scope.row.algBkType" />
        </template>
      </el-table-column>
      <el-table-column label="布控算法api请求头编码"
                       align="center"
                       prop="algBkApiHead" />
      <el-table-column label="启用标志"
                       align="center"
                       prop="status">
        <template slot-scope="scope">
          <dict-tag :options="dict.type.basedata_isvalid"
                    :value="scope.row.status" />
        </template>
      </el-table-column>
      <el-table-column label="设备状态表名"
                       align="center"
                       prop="tableName" />
      <el-table-column label="备注"
                       align="center"
                       prop="remark" />
      <el-table-column label="操作"
                       align="center"
                       class-name="small-padding fixed-width">
        <template slot-scope="scope">
          <el-button size="mini"
                     type="text"
                     icon="el-icon-edit"
                     @click="handleUpdate(scope.row)"
                     v-hasPermi="['algdeployment:algdeploymentmanagement:edit']">修改</el-button>
          <el-button v-if="scope.row.status != 1"
                     size="mini"
                     type="text"
                     icon="el-icon-delete"
                     @click="handleDelete(scope.row)"
                     v-hasPermi="['algdeployment:algdeploymentmanagement:remove']">删除</el-button>
          <el-button v-if="scope.row.status == 1"
                     size="mini"
                     type="text"
                     icon="el-icon-upload"
                     @click="handleDeploy(scope.row)">布控</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0"
                class="table-pagination"
                :total="total"
                :page.sync="queryParams.pageNum"
                :limit.sync="queryParams.pageSize"
                @pagination="getList" />

    <!-- 添加或修改算法布控管理对话框 -->
    <el-dialog :title="title"
               :visible.sync="open"
               width="500px"
               append-to-body>
      <el-form ref="form"
               :model="form"
               :rules="rules"
               label-width="80px">
        <el-form-item label="布控算法名称"
                      prop="algBkName">
          <el-input v-model="form.algBkName"
                    placeholder="请输入布控算法名称" />
        </el-form-item>
        <el-form-item label="布控算法类型"
                      prop="algBkType">
          <el-select v-model="form.algBkType"
                     placeholder="请选择布控算法类型">
            <el-option v-for="dict in dict.type.alg_bk_type"
                       :key="dict.value"
                       :label="dict.label"
                       :value="parseInt(dict.value)"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="布控算法api请求头编码"
                      prop="algBkApiHead">
          <el-input v-model="form.algBkApiHead"
                    placeholder="请输入布控算法api请求头编码" />
        </el-form-item>
        <el-form-item label="启用标志"
                      prop="status">
          <el-radio-group v-model="form.status">
            <el-radio v-for="dict in dict.type.basedata_isvalid"
                      :key="dict.value"
                      :label="parseInt(dict.value)">{{dict.label}}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="设备状态表名"
                      prop="tableName">
          <el-input v-model="form.tableName"
                    :disabled="form.algBkType === 1"
                    placeholder="请输入设备状态表名" />
        </el-form-item>
        <el-form-item label="备注"
                      prop="remark">
          <el-input v-model="form.remark"
                    placeholder="请输入备注" />
        </el-form-item>
      </el-form>
      <div slot="footer"
           class="dialog-footer">
        <el-button type="primary"
                   @click="submitForm">确 定</el-button>
        <el-button @click="cancel">取 消</el-button>
      </div>
    </el-dialog>

    <!-- 设备选择弹窗 -->
    <el-dialog title="选择设备"
               :visible.sync="deviceDialogVisible"
               width="80%"
               top="20vh"
               append-to-body>
      <el-table v-loading="deviceLoading"
                :data="deviceList"
                @selection-change="handleDeviceSelectionChange"
                height="450px"
                :row-style="{height: '50px'}"
                :cell-style="{padding: '5px 0'}"
                border>
        <el-table-column type="selection"
                         width="55"
                         align="center" />
        <el-table-column label="主键"
                         align="center"
                         prop="machine_id"
                         width="80" />
        <el-table-column label="设备编码"
                         align="center"
                         prop="machineCode"
                         width="120" />
        <el-table-column label="设备名称"
                         align="center"
                         prop="machineName"
                         min-width="120" />
        <el-table-column label="设备流"
                         align="center"
                         prop="videoUrl"
                         min-width="150"
                         :show-overflow-tooltip="true" />
        <el-table-column label="分辨率"
                         align="center"
                         prop="resolution"
                         width="100" />
        <el-table-column label="解码器"
                         align="center"
                         prop="decoder"
                         width="100" />
        <el-table-column label="设备状态"
                         align="center"
                         prop="status"
                         width="80">
          <template slot-scope="scope">
            {{ statusMap[scope.row.status] }}
          </template>
        </el-table-column>
        <el-table-column label="启用标志"
                         align="center"
                         prop="isvalid"
                         width="80">
          <template slot-scope="scope">
            {{ isvalidMap[scope.row.isvalid] }}
          </template>
        </el-table-column>
        <el-table-column label="布控状态"
                         align="center"
                         prop="deployStatus"
                         width="80">
        </el-table-column>
      </el-table>
      <div slot="footer"
           class="dialog-footer">
        <el-button type="primary"
                   icon="el-icon-video-play"
                   @click="confirmDeviceSelect">开始布控</el-button>
        <el-button type="danger"
                   icon="el-icon-video-pause"
                   @click="stopDeploy">停止布控</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { listAlgdeploymentmanagement, getAlgdeploymentmanagement, delAlgdeploymentmanagement, addAlgdeploymentmanagement, updateAlgdeploymentmanagement, getMachineList, deployAlg, stopDeploy } from "@/api/algdeployment/alg_deployment_management/index";

export default {
  name: "Algdeploymentmanagement",
  dicts: ['alg_bk_type', 'basedata_isvalid'],
  data () {
    return {
      // 遮罩层
      loading: true,
      // 选中数组
      ids: [],
      // 非单个禁用
      single: true,
      // 非多个禁用
      multiple: true,
      // 显示搜索条件
      showSearch: true,
      // 总条数
      total: 0,
      // 算法布控管理表格数据
      algdeploymentmanagementList: [],
      // 弹出层标题
      title: "",
      // 是否显示弹出层
      open: false,
      // 查询参数
      queryParams: {
        pageNum: 1,
        pageSize: 10,
        algBkName: null,
        algBkType: null,
        status: null,
      },
      // 表单参数
      form: {},
      // 表单校验
      rules: {
      },
      // 设备选择弹窗显示状态
      deviceDialogVisible: false,
      // 设备列表加载状态
      deviceLoading: false,
      // 设备列表数据
      deviceList: [],
      // 选中的设备
      selectedDevices: [],
      // 当前操作的算法数据
      currentAlg: null,
      // 设备状态映射
      statusMap: {
        1: '在线',
        0: '离线',
        2: '检修中...'
      },
      // 启用状态映射
      isvalidMap: {
        1: '是',
        0: '否'
      },
    };
  },
  created () {
    this.getList();
  },
  methods: {
    handleDeploy (row) {
      this.currentAlg = row;
      this.deviceDialogVisible = true;
      this.getDeviceList()
    },
    /** 查询算法布控管理列表 */
    getList () {
      this.loading = true;
      listAlgdeploymentmanagement(this.queryParams).then(response => {
        this.algdeploymentmanagementList = response.rows;
        this.total = response.total;
        this.loading = false;
      });
    },
    // 取消按钮
    cancel () {
      this.open = false;
      this.reset();
    },
    // 表单重置
    reset () {
      this.form = {
        id: null,
        algBkName: null,
        algBkType: null,
        algBkApiHead: null,
        status: null,
        tableName: null,
        remark: null
      };
      this.resetForm("form");
    },
    /** 搜索按钮操作 */
    handleQuery () {
      this.queryParams.pageNum = 1;
      this.getList();
    },
    /** 重置按钮操作 */
    resetQuery () {
      this.resetForm("queryForm");
      this.handleQuery();
    },
    // 多选框选中数据
    handleSelectionChange (selection) {
      this.ids = selection.map(item => item.id)
      this.single = selection.length !== 1
      this.multiple = !selection.length
    },
    /** 新增按钮操作 */
    handleAdd () {
      this.reset();
      this.open = true;
      this.title = "添加算法布控管理";
    },
    /** 修改按钮操作 */
    handleUpdate (row) {
      this.reset();
      const id = row.id || this.ids
      getAlgdeploymentmanagement(id).then(response => {
        this.form = response.data;
        this.open = true;
        this.title = "修改算法布控管理";
      });
    },
    /** 提交按钮 */
    submitForm () {
      this.$refs["form"].validate(valid => {
        if (valid) {
          if (this.form.id != null) {
            updateAlgdeploymentmanagement(this.form).then(response => {
              this.$modal.msgSuccess("修改成功");
              this.open = false;
              this.getList();
            });
          } else {
            addAlgdeploymentmanagement(this.form).then(response => {
              this.$modal.msgSuccess("新增成功");
              this.open = false;
              this.getList();
            });
          }
        }
      });
    },
    /** 删除按钮操作 */
    handleDelete (row) {
      const ids = row.id || this.ids;
      this.$modal.confirm('是否确认删除算法布控管理编号为"' + ids + '"的数据项？').then(function () {
        return delAlgdeploymentmanagement(ids);
      }).then(() => {
        this.getList();
        this.$modal.msgSuccess("删除成功");
      }).catch(() => { });
    },
    /** 导出按钮操作 */
    handleExport () {
      this.download('algdeployment/algdeploymentmanagement/export', {
        ...this.queryParams
      }, `algdeploymentmanagement_${new Date().getTime()}.xlsx`)
    },
    // 获取设备列表
    getDeviceList () {
      this.deviceLoading = true;
      getMachineList(this.deviceQueryParams).then(response => {
        this.deviceList = response.data || [];
        this.deviceTotal = response.total || this.deviceList.length;
        this.deviceLoading = false;
      });
    },
    // 设备多选框选中数据
    handleDeviceSelectionChange (selection) {
      this.selectedDevices = selection;
    },
    // 确认选择设备
    confirmDeviceSelect () {
      if (this.selectedDevices.length === 0) {
        this.$modal.msgError("请选择至少一个设备");
        return;
      }

      // 检查是否有已布控的设备
      var activeDevices = this.selectedDevices.filter(device => device.deployStatus === "active");
      if (activeDevices.length > 0) {
        const deviceNames = activeDevices.map(d => d.machineName).join('、');
        this.$modal.msgError(`设备 ${deviceNames} 已处于布控状态，请先停止布控`);
        return;
      }

      // 开始布控
      this.deviceLoading = true;
      var deployList = [];
      this.selectedDevices.forEach(machine => {
        deployList.push({
          machineId: machine.machine_id,
          videoUrl: machine.videoUrl,
          resolution: machine.resolution,
          codec_type: machine.decoder,
        });
      });

      deployAlg(this.currentAlg.algBkApiHead, deployList)
        .then(response => {
          if (response.code === 200) {
            this.$modal.msgSuccess("布控成功");
            // 清除临时数据
            this.clearTempData();
          } else {
            this.$modal.msgError(response.msg || "布控失败");
            // 清除临时数据并刷新表格
            this.clearTempData();
          }
        })
        .catch(error => {
          this.$modal.msgError("布控失败: " + error.message);
          // 清除临时数据并刷新表格
          this.clearTempData();
        })
        .finally(() => {
          this.deviceLoading = false;
        });
    },
    // 停止布控
    stopDeploy () {
      if (this.selectedDevices.length === 0) {
        this.$modal.msgError("请选择要停止布控的设备");
        return;
      }

      // 检查是否有未布控的设备
      const inactiveDevices = this.selectedDevices.filter(device => device.deployStatus == "inactive");
      if (inactiveDevices.length > 0) {
        const deviceNames = inactiveDevices.map(d => d.machineName).join('、');
        this.$modal.msgError(`设备 ${deviceNames} 未处于布控状态`);
        return;
      }

      this.deviceLoading = true;
      var stopList = [];
      this.selectedDevices.forEach(machine => {
        stopList.push({
          machineId: machine.machine_id,
        });
      });

      stopDeploy(this.currentAlg.algBkApiHead, stopList)
        .then(response => {
          this.$modal.msgSuccess("停止布控成功");
          // 清除临时数据并刷新表格
          this.clearTempData();
        })
        .catch(error => {
          this.$modal.msgError("停止布控失败: " + error.message);
          // 清除临时数据并刷新表格
          this.clearTempData();
        })
        .finally(() => {
          this.deviceLoading = false;
        });
    },
    // 清除临时数据
    clearTempData () {
      this.deviceDialogVisible = false; // 关闭弹窗
      this.selectedDevices = []; // 清空选中设备
      this.currentAlg = null; // 清空当前算法
      this.deviceList = []; // 清空设备列表
      this.getList(); // 刷新主表格数据
      this.getDeviceList(); // 刷新设备列表
    },
    // 批量删除按钮操作
    handleBatchDelete () {
      // 判断是否有启用状态的算法
      const enabled = this.algdeploymentmanagementList.filter(item => this.ids.includes(item.id) && item.status == 1)
      if (enabled.length > 0) {
        this.$modal.msgError('启用状态的算法无法删除');
        return;
      }
      this.handleDelete({id: this.ids});
    }
  }
};
</script>

<style lang="scss" scoped>
.app-container {
  .search-form {
    margin-bottom: 20px;
  }

  .table-toolbar {
    margin-bottom: 15px;
  }

  .main-table {
    margin-bottom: 20px;
  }

  .table-pagination {
    text-align: right;
    padding: 10px 0;
  }
}

</style>
