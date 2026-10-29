<template>
  <div class="app-container">
    <el-form :model="queryParams"
             ref="queryForm"
             size="small"
             :inline="true"
             v-show="showSearch"
             label-width="68px">
      <el-form-item label="模型名称"
                    prop="algmodelName">
        <el-input v-model="queryParams.algmodelName"
                  placeholder="请输入模型名称"
                  clearable
                  @keyup.enter.native="handleQuery" />
      </el-form-item>
      <el-form-item label="模型引擎"
                    prop="algmodelEngines">
        <el-input v-model="queryParams.algmodelEngines"
                  placeholder="请输入模型引擎"
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
                   v-hasPermi="['basedata:algmodel:add']">新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success"
                   plain
                   icon="el-icon-edit"
                   size="mini"
                   :disabled="single"
                   @click="handleUpdate"
                   v-hasPermi="['basedata:algmodel:edit']">修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger"
                   plain
                   icon="el-icon-delete"
                   size="mini"
                   :disabled="multiple"
                   @click="handleDelete"
                   v-hasPermi="['basedata:algmodel:remove']">删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning"
                   plain
                   icon="el-icon-download"
                   size="mini"
                   @click="handleExport"
                   v-hasPermi="['basedata:algmodel:export']">导出</el-button>
      </el-col>
      <right-toolbar :showSearch.sync="showSearch"
                     @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading"
              :data="algmodelList"
              @selection-change="handleSelectionChange">
      <el-table-column type="selection"
                       width="55"
                       align="center" />
      <el-table-column label="主键"
                       align="center"
                       prop="algmodelId" />
      <el-table-column label="模型编码"
                       align="center"
                       prop="algmodelCode" />
      <el-table-column label="模型名称"
                       align="center"
                       prop="algmodelName" />
      <el-table-column label="模型引擎"
                       align="center"
                       prop="algmodelEngines" />
      <el-table-column label="输入"
                       align="center"
                       prop="isvalid">
        <template slot-scope="scope">
          <dict-tag :options="dict.type.basedata_alg_in_out"
                    :value="scope.row.algmodelInput" />
        </template>
      </el-table-column>
      <el-table-column label="输出"
                       align="center"
                       prop="isvalid">
        <template slot-scope="scope">
          <dict-tag :options="dict.type.basedata_alg_in_out"
                    :value="scope.row.algmodelOutput" />
        </template>
      </el-table-column>
      <el-table-column label="模型文件"
                       align="center"
                       prop="path" />
      <el-table-column label="封面图">
        <template slot-scope="scope">
          <img :src="env+scope.row.preview"
               alt="封面图"
               style="max-width: 100px; max-height: 100px;">
        </template>
      </el-table-column>
      <el-table-column label="算法类型"
                       align="center"
                       prop="algtypeName" />
      <el-table-column label="启用"
                       align="center"
                       prop="isvalid">
        <template slot-scope="scope">
          <dict-tag :options="dict.type.basedata_isvalid"
                    :value="scope.row.isvalid" />
        </template>
      </el-table-column>
      <el-table-column label="模型描述"
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
                     v-hasPermi="['basedata:algmodel:edit']">修改</el-button>
          <el-button size="mini"
                     type="text"
                     icon="el-icon-delete"
                     @click="handleDelete(scope.row)"
                     v-hasPermi="['basedata:algmodel:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0"
                :total="total"
                :page.sync="queryParams.pageNum"
                :limit.sync="queryParams.pageSize"
                @pagination="getList" />

    <!-- 添加或修改模型信息对话框 -->
    <el-dialog :title="title"
               :visible.sync="open"
               width="500px"
               append-to-body>
      <el-form ref="form"
               :model="form"
               :rules="rules"
               label-width="80px">
        <el-form-item label="模型编码"
                      prop="algmodelCode">
          <el-input v-model="form.algmodelCode"
                    placeholder="请输入模型编码" />
        </el-form-item>
        <el-form-item label="模型名称"
                      prop="algmodelName">
          <el-input v-model="form.algmodelName"
                    placeholder="请输入模型名称" />
        </el-form-item>
        <el-form-item label="模型引擎"
                      prop="algmodelEngines">
          <el-input v-model="form.algmodelEngines"
                    placeholder="请输入模型引擎" />
        </el-form-item>
        <el-form-item label="算法输入"
                      prop="algmodelInput">
          <el-select v-model="form.algmodelInput"
                     clearable
                     placeholder="请选择">
            <el-option v-for="dict in dict.type.basedata_alg_in_out"
                       :key="dict.value"
                       :label="dict.label"
                       :value="dict.value">
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="算法输出"
                      prop="algmodelOutput">
          <el-select v-model="form.algmodelOutput"
                     clearable
                     placeholder="请选择">
            <el-option v-for="dict in dict.type.basedata_alg_in_out"
                       :key="dict.value"
                       :label="dict.label"
                       :value="dict.value">
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="模型文件"
                      prop="path">
          <el-upload class="model-uploader"
                     action="#"
                     :show-file-list="true"
                     :before-upload="handleModelFileUpload"
                     :file-list="modelFileList">
            <el-button size="small"
                       type="primary">选择模型文件</el-button>
            <div slot="tip"
                 class="el-upload__tip">请上传模型文件</div>
          </el-upload>
        </el-form-item>
        <el-form-item label="算法类型"
                      prop="algtypeId">
          <el-select v-model="form.algtypeId"
                     clearable
                     placeholder="请选择">
            <el-option v-for="item in algTypeOptions"
                       :key="item.value"
                       :label="item.lable"
                       :value="item.value">
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-radio-group v-model="form.isvalid">
            <el-radio v-for="dict in dict.type.basedata_isvalid"
                      :key="Number(dict.value)"
                      :label="Number(dict.value)">{{dict.label}}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="模型描述"
                      prop="remark">
          <el-input v-model="form.remark"
                    placeholder="请输入模型描述" />
        </el-form-item>
        <el-form-item label="封面图">
          <el-upload action="#"
                     :show-file-list="false"
                     :before-upload="beforeUpload">
            <el-button size="small">
              选择
              <i class="el-icon-upload el-icon--right"></i>
            </el-button>
          </el-upload>
          <!-- 图片预览 -->
          <img v-if="imgUrl"
               :src="imgUrl"
               alt="Image Preview"
               style="max-width: 100%; margin-top: 10px;" />
        </el-form-item>
      </el-form>
      <div slot="footer"
           class="dialog-footer">
        <el-button type="primary"
                   @click="submitForm">确 定</el-button>
        <el-button @click="cancel">取 消</el-button>
      </div>
      <div v-if="uploading" class="upload-progress">
        <el-progress 
          :percentage="uploadProgress" 
          :format="format"
          :stroke-width="15"
          status="success">
        </el-progress>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { listAlgmodel, getAlgmodel, delAlgmodel, addAlgmodel, updateAlgmodel } from "@/api/basedata/algmodel";
import { listAlgtype } from "@/api/basedata/algtype";
import { uploadModelFile } from "@/api/algorithm";

export default {
  dicts: ['basedata_isvalid', 'basedata_alg_in_out'],
  name: "Algmodel",
  data () {
    return {
      env: process.env.VUE_APP_BASE_API, // 用于存储环境变量
      // 图片地址
      imgUrl: null,
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
      // 条数
      total: 0,
      // 模型信息表格数据
      algmodelList: [],
      // 弹出层标题
      title: "",
      // 是否显示弹出层
      open: false,
      //算法类型
      algTypeOptions: [],
      // 查询参数
      queryParams: {
        pageNum: 1,
        pageSize: 10,
        algmodelName: null,
        algmodelEngines: null,
        isvalid: null,
      },
      // 表单参
      form: {},
      // 表单校验
      rules: {
        algmodelName: [
          { required: true, message: "模型名称不能为空", trigger: "blur" }
        ],
      },
      modelFileList: [], // 用于存储模型文件列表
      uploadProgress: 0,
      uploading: false
    };
  },
  created () {
    this.getList();
  },
  methods: {
    /** 查询模型信息列表 */
    getList () {
      this.algTypeOptions = [];
      this.loading = true;
      listAlgmodel(this.queryParams).then(response => {
        this.algmodelList = response.rows;
        this.total = response.total;
        this.loading = false;
      });
      listAlgtype({}).then(response => {
        const data = response.rows
        data.forEach(el => {
          var temp = {
            lable: el.algtypeName,
            value: el.algtypeId
          }
          this.algTypeOptions.push(temp)
        });
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
        algmodelId: null,
        algmodelCode: null,
        algmodelName: null,
        algmodelEngines: null,
        path: null,
        modelFile: null,
        algtypeId: null,
        isvalid: 1,
        remark: null,
        preview: null,
        imgData: null
      };
      this.imgUrl = null;
      this.modelFileList = []; // 清空文件列表
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
      this.ids = selection.map(item => item.algmodelId)
      this.single = selection.length !== 1
      this.multiple = !selection.length
    },
    /** 新增按钮操作 */
    handleAdd () {
      this.reset();
      this.open = true;
      this.title = "添加模型信息";
    },
    /** 修改按钮操作 */
    handleUpdate (row) {
      this.reset();
      const algmodelId = row.algmodelId || this.ids
      getAlgmodel(algmodelId).then(response => {
        this.form = response.data;
        this.imgUrl = this.env + this.form.preview;
        // 如果有模型文件路径，添加到文件列表中
        if (this.form.path) {
          this.modelFileList = [{
            name: this.form.path.split('/').pop(), // 获取文件名
            url: this.env + this.form.path // 完整的文件路径
          }];
        }
        this.open = true;
        this.title = "修改模型信息";
      });
    },
    /** 提交按钮 */
    async submitForm() {
      try {
        const valid = await this.$refs["form"].validate();
        if (valid) {
          if (this.form.modelFile) {
            this.uploading = true;
            const modelFormData = new FormData();
            modelFormData.append('model_file', this.form.modelFile);
            modelFormData.append('model_name', this.form.algmodelName);
            modelFormData.append('model_code', this.form.algmodelCode);

            // 上传模型文件并显示进度
            const modelResponse = await uploadModelFile(
              modelFormData,
              progress => {
                this.uploadProgress = progress;
              }
            );

            if (modelResponse.model_info) {
              this.form.path = modelResponse.model_info.filename;
            } else {
              this.$message.error('模型文件上传失败');
              return;
            }
          }

          // 继续提交表单其他数据
          const formData = new FormData();
          
          // 添加模型基本信息
          formData.append('baAlgmodel', new Blob([JSON.stringify({
            ...this.form,
            path: this.form.path
          })], { type: 'application/json' }));

          // 添加封面图
          if (this.form.imgData) {
            formData.append('imgData', this.form.imgData.imageBlob, this.form.imgData.filename);
          }

          const request = this.form.algmodelId != null ? updateAlgmodel : addAlgmodel;
          const response = await request(formData);
          
          this.$modal.msgSuccess(this.form.algmodelId != null ? "修改成功" : "新增成功");
          this.open = false;
          this.getList();
        }
      } catch (error) {
        console.error('提交失败:', error);
        this.$message.error('提交失败，请重试');
      } finally {
        this.uploading = false;
        this.uploadProgress = 0;
      }
    },
    /** 删除按钮操作 */
    handleDelete (row) {
      const algmodelIds = row.algmodelId || this.ids;
      this.$modal.confirm('是否确认删除模型信息编号为"' + algmodelIds + '"的数据项？').then(function () {
        return delAlgmodel(algmodelIds);
      }).then(() => {
        this.getList();
        this.$modal.msgSuccess("删除成功");
      }).catch(() => { });
    },
    /** 导出按钮操作 */
    handleExport () {
      this.download('basedata/algmodel/export', {
        ...this.queryParams
      }, `algmodel_${new Date().getTime()}.xlsx`)
    },
    beforeUpload (file) {
      // 检查文件类型
      if (file.type.indexOf("image/") === -1) {
        this.$modal.msgError("文件格式错误，请上传图片类型,如：JPG，PNG后缀的文件。");
        return false;
      }
      // 使用FileReader读取文件
      const reader = new FileReader();
      reader.readAsDataURL(file);
      // 将base64转换为blob
      reader.onload = () => {
        const result = reader.result;
        const base64Data = typeof result === 'string'
          ? (result.includes('base64:')
            ? result.split('base64:')[1]
            : result.split(',')[1])
          : '';
        const byteCharacters = atob(base64Data);
        const byteArrays = [];

        for (let offset = 0; offset < byteCharacters.length; offset += 512) {
          const slice = byteCharacters.slice(offset, offset + 512);
          const byteNumbers = new Array(slice.length);

          for (let i = 0; i < slice.length; i++) {
            byteNumbers[i] = slice.charCodeAt(i);
          }

          const byteArray = new Uint8Array(byteNumbers);
          byteArrays.push(byteArray);
        }

        const blob = new Blob(byteArrays, { type: file.type });
        this.imgUrl = reader.result;// 用于预览显示
        this.form.imgData = {
          filename: file.name,
          imageBlob: blob
        };
      };
      return false; // 阻止默认上传行为
    },
    handleModelFileUpload(file) {
      // 检查文件类型（可以根据需要添加）
      const allowedTypes = ['.whl'];
      const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
      if (!allowedTypes.includes(extension)) {
        this.$message.error(`只能上传 ${allowedTypes.join('/')} 格式的文件`);
        return false;
      }
      // 保存文件对象到表单数据
      this.form.modelFile = file;
      // 显示文件名
      this.form.path = file.name;
      // 更新文件列表显示
      this.modelFileList = [{
        name: file.name,
        url: URL.createObjectURL(file)
      }];
      return false;
    },
    // 添加格式化方法
    format(percentage) {
      if (percentage === 100) {
        return '上传完成';
      }
      return `上传中 ${percentage}%`;
    }
  }
};
</script>

<style lang="scss">
.app-container.algmodel-container {
  .el-dialog {
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);

    .el-dialog__header {
      background: #f8f9fb;
      padding: 20px;
      border-bottom: 1px solid #ebeef5;

      .el-dialog__title {
        font-size: 18px;
        font-weight: 600;
        color: #303133;
      }
    }

    .el-dialog__body {
      padding: 30px !important;
    }

    .el-form {
      .el-form-item {
        margin-bottom: 25px !important;

        &:last-child {
          margin-bottom: 0;
        }

        .el-form-item__label {
          font-weight: 500;
          color: #606266;
          padding-right: 20px;
        }

        .el-input__inner {
          height: 40px;
          line-height: 40px;
          border-radius: 4px;
          border: 1px solid #dcdfe6;
          transition: all 0.3s;

          &:hover {
            border-color: #c0c4cc;
          }

          &:focus {
            border-color: #409eff;
            box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
          }
        }

        .el-select {
          width: 100%;
        }

        .el-radio-group {
          .el-radio {
            margin-right: 20px;
            margin-bottom: 0;

            .el-radio__label {
              font-size: 14px;
            }
          }
        }
      }
    }

    .model-uploader {
      .el-upload {
        width: 100%;

        .el-button {
          width: 100%;
          background: linear-gradient(135deg, #409eff, #3a8ee6);
          border: none;
          padding: 12px 20px;
          font-size: 14px;
          transition: all 0.3s;

          &:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
          }

          i {
            margin-right: 8px;
          }
        }
      }

      .el-upload__tip {
        color: #909399;
        font-size: 12px;
        margin-top: 8px;
        line-height: 1.4;
      }

      .el-upload-list {
        margin-top: 15px;
        border: 1px solid #ebeef5;
        border-radius: 4px;
        padding: 5px 0;

        .el-upload-list__item {
          transition: all 0.3s;
          margin: 0;
          padding: 10px 15px;

          &:not(:last-child) {
            border-bottom: 1px solid #ebeef5;
          }

          &:hover {
            background-color: #f5f7fa;
          }

          .el-upload-list__item-name {
            color: #606266;
            font-size: 14px;
            line-height: 1.4;
            padding-left: 0;
            display: flex;
            align-items: center;

            i {
              margin-right: 8px;
              color: #409eff;
              font-size: 16px;
            }
          }
        }
      }
    }

    .dialog-footer {
      padding: 20px;
      text-align: right;
      background: #f8f9fb;
      border-top: 1px solid #ebeef5;

      .el-button {
        padding: 12px 25px;
        font-size: 14px;
        font-weight: 500;
        transition: all 0.3s;

        &:not(.el-button--primary) {
          border-color: #dcdfe6;

          &:hover {
            color: #409eff;
            border-color: #c6e2ff;
            background-color: #ecf5ff;
          }
        }

        &.el-button--primary {
          background: linear-gradient(135deg, #409eff, #3a8ee6);
          border: none;

          &:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
          }
        }
      }
    }
  }
}

.upload-progress {
  margin: 20px 0;
  padding: 15px;
  background: rgba(64, 158, 255, 0.1);
  border-radius: 4px;
  border: 1px solid rgba(64, 158, 255, 0.2);

  .el-progress-bar__outer {
    background-color: rgba(255, 255, 255, 0.3);
  }

  .el-progress-bar__inner {
    background: linear-gradient(90deg, #409eff, #3a8ee6);
  }

  .el-progress__text {
    color: #409eff;
    font-size: 13px;
    font-weight: 500;
  }
}
</style>
