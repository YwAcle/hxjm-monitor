<template>
  <div class="app-container">
    <el-form :model="queryParams"
             ref="queryForm"
             size="small"
             :inline="true"
             v-show="showSearch"
             label-width="68px">
      <el-form-item label="设备名称"
                    prop="machineName">
        <el-input v-model="queryParams.machineName"
                  placeholder="请输入设备名称"
                  clearable
                  @keyup.enter.native="handleQuery" />
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
            class="mb8">
      <el-col :span="1.5">
        <el-button type="primary"
                   plain
                   icon="el-icon-plus"
                   size="mini"
                   @click="handleAdd"
                   v-hasPermi="['basedata:machine:add']">新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success"
                   plain
                   icon="el-icon-edit"
                   size="mini"
                   :disabled="single"
                   @click="handleUpdate"
                   v-hasPermi="['basedata:machine:edit']">修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger"
                   plain
                   icon="el-icon-delete"
                   size="mini"
                   :disabled="multiple"
                   @click="handleDelete"
                   v-hasPermi="['basedata:machine:remove']">删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning"
                   plain
                   icon="el-icon-download"
                   size="mini"
                   @click="handleExport"
                   v-hasPermi="['basedata:machine:export']">导出</el-button>
      </el-col>
      <right-toolbar :showSearch.sync="showSearch"
                     @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading"
              :data="machineList"
              @selection-change="handleSelectionChange">
      <el-table-column type="selection"
                       width="55"
                       align="center" />
      <el-table-column label="主键"
                       align="center"
                       prop="machineId" />
      <el-table-column label="设备编码"
                       align="center"
                       prop="machineCode" />
      <el-table-column label="设备名称"
                       align="center"
                       prop="machineName" />
      <el-table-column label="设备流"
                       align="center"
                       prop="videoUrl" />
      <el-table-column label="分辨率"
                       align="center"
                       prop="resolution" />
      <el-table-column label="解码器"
                       align="center"
                       prop="decoder" />
      <el-table-column label="设备状态"
                       align="center"
                       prop="status">
        <template slot-scope="scope">
          {{ statusMap[scope.row.status]  }}
        </template>
      </el-table-column>
      <el-table-column label="启用标志"
                       align="center"
                       prop="isvalid">
        <template slot-scope="scope">
          {{ isvalidMap[scope.row.isvalid] }}
        </template>
      </el-table-column>
      <el-table-column label="操作"
                       align="center"
                       class-name="small-padding fixed-width">
        <template slot-scope="scope">
          <el-button size="mini"
                     type="text"
                     icon="el-icon-edit"
                     @click="handleUpdate(scope.row)"
                     v-hasPermi="['basedata:machine:edit']">修改</el-button>
          <el-button size="mini"
                     type="text"
                     icon="el-icon-delete"
                     @click="handleDelete(scope.row)"
                     v-hasPermi="['basedata:machine:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0"
                :total="total"
                :page.sync="queryParams.pageNum"
                :limit.sync="queryParams.pageSize"
                @pagination="getList" />

    <!-- 添加或修改设备信息对话框 -->
    <el-dialog :title="title"
               :visible.sync="open"
               width="500px"
               append-to-body>
      <el-form ref="form"
               :model="form"
               :rules="rules"
               label-width="80px">
        <el-form-item label="设备编码"
                      prop="machineCode">
          <el-input v-model="form.machineCode"
                    placeholder="请输入设备编码" />
        </el-form-item>
        <el-form-item label="设备名称"
                      prop="machineName">
          <el-input v-model="form.machineName"
                    placeholder="请输入设备名称" />
        </el-form-item>
        <el-form-item label="设备流"
                      prop="videoUrl">
          <el-input v-model="form.videoUrl"
                    placeholder="请输入设备流" />
        </el-form-item>
        <el-form-item label="分辨率"
                      prop="resolution">
          <el-input v-model="form.resolution"
                    placeholder="请输入分辨率" />
        </el-form-item>
        <el-form-item label="解码器"
                      prop="decoder">
          <el-input v-model="form.decoder"
                    placeholder="请输入解码器" />
        </el-form-item>
        <el-form-item label="所属区域id"
                      prop="locationId">
          <el-input v-model="form.locationId"
                    placeholder="请输入所属区域id" />
        </el-form-item>
        <el-form-item label="设备状态"
                      prop="status">
          <el-select v-model="form.status"
                     placeholder="请选择设备状态">
            <el-option v-for="(value, key) in statusMap"
                       :key="key"
                       :label="value"
                       :value="key"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="启用状态"
                      prop="isvalid">
          <el-select v-model="form.isvalid"
                     placeholder="请选择启用状态">
            <el-option v-for="(value, key) in isvalidMap"
                       :key="key"
                       :label="value"
                       :value="key"></el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <div slot="footer"
           class="dialog-footer">
        <el-button type="primary"
                   @click="submitForm">确 定</el-button>
        <el-button @click="cancel">取 消</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { listMachine, getMachine, delMachine, addMachine, updateMachine } from "@/api/basedata/machine";

export default {
  name: "Machine",
  data () {
    return {
      statusMap: {
        1: '在线',
        0: '离线',
        2: '检修中...'
      },
      isvalidMap: {
        1: '是',
        0: '否'
      },
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
      // 设备信息表格数据
      machineList: [],
      // 弹出层标题
      title: "",
      // 是否显示弹出层
      open: false,
      // 查询参数
      queryParams: {
        pageNum: 1,
        pageSize: 10,
        machineName: null,
        status: null,
      },
      // 表单参数
      form: {
        machineId: null,
        machineCode: null,
        machineName: null,
        videoUrl: null,
        resolution: null,
        decoder: null,
        locationId: null,
        status: null,
        isvalid: null
      },
      // 表单校验
      rules: {
        machineName: [
          { required: true, message: "设备名称不能为空", trigger: "blur" }
        ],
        videoUrl: [
          { required: true, message: "设备流不能为空", trigger: "blur" }
        ],
        resolution: [
          { required: true, message: "分辨率不能为空", trigger: "blur" }
        ],
        decoder: [
          { required: true, message: "解码器不能为空", trigger: "blur" }
        ]
      }
    };
  },
  created () {
    this.getList();
  },
  methods: {
    /** 查询设备信息列表 */
    getList () {
      this.loading = true;
      listMachine(this.queryParams).then(response => {
        this.machineList = response.rows;
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
        machineId: null,
        machineCode: null,
        machineName: null,
        videoUrl: null,
        resolution: null,
        decoder: null,
        locationId: null,
        status: null,
        isvalid: null
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
      this.ids = selection.map(item => item.machineId)
      this.single = selection.length !== 1
      this.multiple = !selection.length
    },
    /** 新增按钮操作 */
    handleAdd () {
      this.reset();
      this.open = true;
      this.title = "添加设备信息";
    },
    /** 修改按钮操作 */
    handleUpdate (row) {
      this.reset();
      const machineId = row.machineId || this.ids
      getMachine(machineId).then(response => {
        this.form = response.data;
        this.open = true;
        this.title = "修改设备信息";
      });
    },
    /** 提交按钮 */
    submitForm () {
      this.$refs["form"].validate(valid => {
        if (valid) {
          if (this.form.machineId != null) {
            updateMachine(this.form).then(response => {
              this.$modal.msgSuccess("修改成功");
              this.open = false;
              this.getList();
            });
          } else {
            addMachine(this.form).then(response => {
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
      const machineIds = row.machineId || this.ids;
      this.$modal.confirm('是否确认删除设备信息编号为"' + machineIds + '"的数据项？').then(function () {
        return delMachine(machineIds);
      }).then(() => {
        this.getList();
        this.$modal.msgSuccess("删除成功");
      }).catch(() => { });
    },
    /** 导出按钮操作 */
    handleExport () {
      this.download('basedata/machine/export', {
        ...this.queryParams
      }, `machine_${new Date().getTime()}.xlsx`)
    }
  }
};
</script>
