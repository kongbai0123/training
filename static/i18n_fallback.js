const I18N_TEXT_KEYS = new Map([
  ["Dashboard Control Center", "dashboard.title"],
  ["Control the active project workflow and jump to the next operation.", "dashboard.subtitle"],
  ["Recent Projects", "dashboard.recentProjects"],
  ["Project History", "dashboard.projectHistory"],
  ["New Project", "common.newProject"],
  ["Refresh", "common.refresh"],
  ["Browse History", "browseHistory"],
  ["No project opened", "common.noProjectOpened"],
  ["No project loaded", "common.noProjectLoaded"],
  ["No project open", "common.noProjectOpened"],
  ["Current Project", "common.currentProject"],
  ["Project Context", "common.projectContext"],
  ["Next Suggested Actions", "common.nextSuggestedActions"],
  ["Warnings", "common.warnings"],
  ["Notes", "common.notes"],
  ["System Status", "common.systemStatus"],
  ["Healthy", "common.healthy"],
  ["Checking", "common.checking"],
  ["Save", "headerSave"],
  ["Light", "themeToggle"],
  ["Dark", "themeToggleDark"],
  ["Clear", "common.clear"],
  ["Open", "historyOpen"],
  ["Delete", "historyDelete"],
  ["Cancel", "common.cancel"],
  ["Create Project", "common.createProject"],
  ["Project name", "common.projectName"],
  ["Training mode", "common.trainingMode"],
  ["Task type", "common.taskType"],
  ["Target labels", "common.targetLabels"],
  ["Class list", "common.classList"],
  ["Add", "common.add"],

  ["Dataset", "dataset.titleShort"],
  ["Dataset Status", "dataset.status"],
  ["Dataset Manager", "dataset.title"],
  ["Dataset Import Center", "dataset.importTitle"],
  ["Import", "dataset.importButton"],
  ["Image Browser", "dataset.browserTitle"],
  ["Search image", "dataset.searchPlaceholder"],
  ["Run Quality Check", "dataset.qualityCheck"],
  ["Images", "dataset.images"],
  ["Videos", "dataset.videos"],
  ["Quality", "dataset.quality"],
  ["Duplicates", "dataset.duplicates"],
  ["Invalid", "dataset.invalid"],

  ["Split", "split.titleShort"],
  ["Split Status", "split.status"],
  ["Run Split", "split.run"],
  ["Split file", "split.file"],
  ["Create Split", "split.create"],
  ["Leakage Risk", "split.leakageRisk"],
  ["Low", "common.low"],
  ["Unknown", "common.unknown"],
  ["None", "common.none"],
  ["Not run", "common.notRun"],
  ["Done", "common.done"],
  ["Connected", "common.connected"],
  ["Disconnected", "common.disconnected"],

  ["Augmentation Status", "augmentation.status"],
  ["Preview & Validation", "augmentation.previewValidation"],
  ["Risk Check", "augmentation.riskCheck"],
  ["Preview image", "augmentation.previewImage"],
  ["Original", "augmentation.original"],
  ["Augmented", "augmentation.augmented"],
  ["Reset", "common.reset"],
  ["Apply to Train Split", "augmentation.applyToTrain"],
  ["Custom Settings", "augmentation.customSettings"],
  ["Job History", "common.jobHistory"],
  ["Risk level", "augmentation.riskLevel"],
  ["Target", "common.target"],

  ["Training Status", "training.status"],
  ["Training Context", "training.context"],
  ["Training Control Console", "training.title"],
  ["Training Configuration", "training.config.title"],
  ["Training configuration is locked until readiness checks pass.", "training.config.locked"],
  ["Run Name", "training.runName"],
  ["Model", "training.model"],
  ["Model Registry Preview", "training.modelRegistry.title"],
  ["Import Model", "training.modelRegistry.import"],
  ["Built-in Models", "training.modelRegistry.builtIn"],
  ["Imported Models", "training.modelRegistry.imported"],
  ["Project Trained Models", "training.modelRegistry.projectTrained"],
  ["Model Hub", "training.modelRegistry.hub"],
  ["Selected", "training.modelRegistry.selected"],
  ["Source", "training.modelRegistry.source"],
  ["Built-in candidate", "training.modelRegistry.sourceBuiltIn"],
  ["Backend", "training.modelRegistry.backend"],
  ["Task", "training.modelRegistry.task"],
  ["License status", "training.modelRegistry.license"],
  ["Commercial license review required", "training.modelRegistry.licenseReview"],
  ["Compatible with current task", "training.modelRegistry.compatible"],
  ["May be incompatible", "training.modelRegistry.incompatible"],
  ["Instance Segmentation", "training.task.instanceSegmentation"],
  ["Detection", "training.task.detection"],
  ["Training Profile", "training.profile"],
  ["Epochs", "training.epochs"],
  ["Batch Size", "training.batch"],
  ["Image Size", "training.imgsz"],
  ["Hardware Device", "training.device"],
  ["Learning Rate", "training.lr"],
  ["Optimizer", "training.optimizer"],
  ["Start Training", "training.start"],
  ["Stop Training", "training.stop"],
  ["Live Training Monitor", "training.monitor.title"],
  ["No active training run.", "training.monitor.emptyTitle"],
  ["Progress", "training.monitor.progress"],
  ["Loss", "training.monitor.loss"],
  ["Metrics Dashboard", "training.metrics.title"],
  ["No training metrics yet.", "training.metrics.emptyTitle"],
  ["Primary Metrics", "training.metrics.primary"],
  ["Loss Breakdown", "training.metrics.lossBreakdown"],
  ["Mask Metrics", "training.metrics.mask"],
  ["Box Metrics", "training.metrics.box"],
  ["Report View", "training.metrics.report"],
  ["Convergence Diagnostic", "training.convergence"],
  ["History & Event Logs", "training.logs.title"],
  ["Epoch History", "training.logs.epochHistory"],
  ["Event Log", "training.logs.eventLog"],
  ["Model Artifacts", "training.artifacts.title"],
  ["Run History", "training.runHistory.title"],
  ["Training Readiness: Blocked", "training.readiness.blocked"],
  ["Training Readiness: Ready", "training.readiness.ready"],

  ["Ready", "common.ready"],
  ["Blocked", "common.blocked"],
  ["Missing", "common.missing"],
  ["Not ready", "common.notReady"],
  ["Not Ready", "common.notReady"],
  ["Not started", "common.notStarted"],
  ["Available", "common.available"],
  ["Unavailable", "common.unavailable"],
  ["Exists", "common.exists"],
  ["Complete", "common.complete"],
  ["Completed", "common.completed"],
  ["Failed", "common.failed"],
  ["Stopped", "common.stopped"],
  ["Running", "common.running"],

  ["RNN Training", "rnn.training.title"],
  ["Start RNN", "rnn.training.start"],
  ["Start RNN Disabled", "rnn.training.startDisabled"],
  ["Feature columns", "rnn.features.columns"],
  ["Target column", "rnn.features.target"],
  ["Feature dim", "rnn.features.dim"],
  ["Sequence length", "rnn.window.sequenceLength"],
  ["Stride", "rnn.window.stride"],
  ["Horizon", "rnn.window.horizon"],
  ["Readiness", "rnn.readiness"],
  ["CSV required", "rnn.csvRequired"],
  ["Sequence count", "rnn.sequenceCount"],
  ["Window config", "rnn.window.config"],
  ["RNN / XGBoost Evaluation", "rnn.evaluation.title"],
  ["Refresh Evaluation", "rnn.evaluation.refresh"],
  ["Artifacts", "training.artifacts.shortTitle"],
  ["Refresh Models", "rnn.models.refresh"],
  ["Sequences", "rnn.inference.sequences"],
  ["Predictions", "rnn.inference.predictions"],
  ["Prediction", "rnn.inference.prediction"],
  ["Confidence", "rnn.inference.confidence"],
  ["Model Guide", "modelGuide.title"],
  ["LSTM Classification", "modelGuide.lstmClassification"],
  ["LSTM Regression", "modelGuide.lstmRegression"],
  ["GRU Classification", "modelGuide.gruClassification"],
  ["GRU Regression", "modelGuide.gruRegression"],
  ["BiLSTM Classification", "modelGuide.biLstmClassification"],
  ["BiLSTM Regression", "modelGuide.biLstmRegression"],
  ["XGBoost Classification", "modelGuide.xgbClassification"],
  ["XGBoost Regression", "modelGuide.xgbRegression"],
  ["Loading model guide...", "modelGuide.loading"],

  ["Evaluation Status", "evaluation.status"],
  ["Run Evaluation", "evaluation.run"],
  ["Inference Status", "inference.status"],
  ["Inference Lab", "inference.title"],
  ["Open Inference Lab", "inference.open"],
  ["Run Inference", "inference.run"],
  ["Task mismatch", "inference.taskMismatch"],
  ["Inference completed", "inference.completed"],
  ["Auto-Labeling Status", "autoLabel.status"],
  ["Start Auto-Labeling", "autoLabel.startAutoLabeling"],
  ["Available models", "autoLabel.stat.models"],
  ["Draft Preview / Review", "autoLabel.previewTitle"],
  ["Export Status", "export.status"],
  ["Export Model", "export.model"],
  ["Last export", "export.lastExport"],
  ["Report", "export.reportTitle"],
  ["Error", "common.error"],
]);

const ZH_TEXT = new Map([
  ["Dashboard Control Center", "總覽控制中心"],
  ["Control the active project workflow and jump to the next operation.", "管理目前專案流程，並快速前往下一個操作。"],
  ["Recent Projects", "最近專案"],
  ["Projects", "專案"],
  ["Browse, open, and manage projects. New projects are created in a modal dialog.", "瀏覽、開啟與管理專案。新專案會在視窗中建立。"],
  ["Project History", "專案歷史"],
  ["Project creation now opens as a modal; this area keeps project browsing, opening, and deletion.", "建立專案會以視窗開啟；此區保留專案瀏覽、開啟與刪除。"],
  ["New Project", "新增專案"],
  ["Refresh", "重新整理"],
  ["Browse History", "瀏覽歷史"],
  ["No project opened", "尚未開啟專案"],
  ["No project loaded", "尚未載入專案"],
  ["No project open", "尚未開啟專案"],
  ["Current Project", "目前專案"],
  ["Project Context", "專案內容"],
  ["Next Suggested Actions", "下一步建議"],
  ["Warnings", "警告"],
  ["Notes", "備註"],
  ["System Status", "系統狀態"],
  ["Healthy", "正常"],
  ["Checking", "檢查中"],
  ["Save", "存檔"],
  ["Light", "明亮"],
  ["Dark", "深色"],
  ["Clear", "清除"],
  ["Open", "開啟"],
  ["Delete", "刪除"],
  ["Cancel", "取消"],
  ["Create Project", "建立專案"],
  ["Create a training project. It will be opened automatically after creation.", "建立訓練專案。建立完成後會自動開啟。"],
  ["Project name", "專案名稱"],
  ["Training mode", "訓練模式"],
  ["Task type", "任務類型"],
  ["Target labels", "目標標籤"],
  ["Class list", "類別清單"],
  ["Add", "新增"],
  ["Optional labels, e.g. normal, abnormal", "可選標籤，例如 normal, abnormal"],

  ["Dataset", "資料集"],
  ["Dataset Status", "資料集狀態"],
  ["Dataset Manager", "資料集管理"],
  ["Dataset Import Center", "資料匯入中心"],
  ["Import", "匯入"],
  ["Upload ZIP or folder", "上傳 ZIP 或資料夾"],
  ["Upload video file", "上傳影片檔"],
  ["Image Browser", "圖片瀏覽"],
  ["Search image", "搜尋圖片"],
  ["Run Quality Check", "執行品質檢查"],
  ["Images", "圖片"],
  ["Videos", "影片"],
  ["Quality", "品質"],
  ["Duplicates", "重複"],
  ["Invalid", "無效"],
  ["No images imported.", "尚未匯入圖片。"],
  ["Import images or a folder.", "匯入圖片或資料夾。"],
  ["Run quality check before labeling.", "標註前先執行品質檢查。"],

  ["LabelMe Status", "LabelMe 狀態"],
  ["Backend Connected", "後端已連線"],
  ["Import Label Files", "匯入標註檔"],
  ["Import with mapping", "依對應匯入"],
  ["Images folder is opened by LabelMe. JSON folder stores annotation output.", "圖片資料夾會由 LabelMe 開啟；JSON 資料夾用來存放標註輸出。"],
  ["Output", "輸出"],
  ["Classes", "類別"],
  ["Command", "指令"],
  ["Open LabelMe", "開啟 LabelMe"],
  ["Refresh Status", "重新整理狀態"],
  ["Annotation Import Report", "標註匯入報告"],
  ["Apply valid drafts", "套用有效草稿"],
  ["Status", "狀態"],
  ["Preview", "預覽"],
  ["Export Formats", "匯出格式"],
  ["Open after JSON checks pass", "JSON 檢查通過後可開啟"],
  ["Semantic Mask", "語意遮罩"],
  ["Copy", "複製"],
  ["Missing JSON", "缺少 JSON"],

  ["Split Status", "資料分散狀態"],
  ["Train / Val / Test Settings", "Train / Val / Test 設定"],
  ["Run Split", "執行分散"],
  ["Split", "資料分散"],
  ["Split file", "分散檔案"],
  ["Create Split", "建立分散"],
  ["Train / Val / Test", "Train / Val / Test"],
  ["Leakage Risk", "洩漏風險"],
  ["Low", "低"],
  ["Unknown", "未知"],
  ["None", "無"],
  ["Not run", "尚未執行"],
  ["Done", "完成"],
  ["Connected", "已連線"],
  ["Disconnected", "未連線"],

  ["Augmentation Status", "物理擴充狀態"],
  ["Preview & Validation", "預覽與驗證"],
  ["Risk Check", "風險檢查"],
  ["Preview required", "需要預覽"],
  ["Preview Ready", "預覽完成"],
  ["Preview ready", "預覽完成"],
  ["Preview stale", "預覽已過期"],
  ["Preview failed", "預覽失敗"],
  ["Generate Preview", "產生預覽"],
  ["Preview image", "預覽圖片"],
  ["Original", "原圖"],
  ["Augmented", "擴充後"],
  ["Reset", "重設"],
  ["Apply to Train Split", "套用到 Train Split"],
  ["Custom Settings", "自訂設定"],
  ["Job History", "作業紀錄"],
  ["Risk level", "風險等級"],
  ["Target", "目標"],
  ["Train split", "Train 分割"],

  ["Training Status", "訓練狀態"],
  ["Training Context", "訓練內容"],
  ["Training Control Console", "模型訓練控制台"],
  ["Training Configuration", "訓練設定"],
  ["Training configuration is locked until readiness checks pass.", "訓練設定會在就緒檢查通過後解鎖。"],
  ["Run Name", "Run 名稱"],
  ["Model", "模型"],
  ["Model Registry Preview", "模型登錄預覽"],
  ["Catalog-driven model selector. Imported YOLO .pt / .yaml models can be used for CNN/YOLO training.", "由模型目錄產生的選擇器。匯入的 YOLO .pt / .yaml 可用於 CNN/YOLO 訓練。"],
  ["Import Model", "匯入模型"],
  ["Built-in Models", "內建模型"],
  ["Imported Models", "匯入模型"],
  ["Project Trained Models", "專案訓練模型"],
  ["No models", "沒有模型"],
  ["Model Hub", "模型中心"],
  ["Selected", "目前選擇"],
  ["Source", "來源"],
  ["Built-in candidate", "內建候選"],
  ["Backend", "後端"],
  ["Task", "任務"],
  ["License status", "授權狀態"],
  ["Commercial license review required", "需自行確認授權狀態"],
  ["Compatible with current task", "與目前任務相容"],
  ["May be incompatible", "可能不相容"],
  ["Instance Segmentation", "實例分割"],
  ["Detection", "偵測"],
  ["Training Profile", "訓練設定檔"],
  ["Balanced", "平衡"],
  ["Quick Test", "快速測試"],
  ["High Accuracy", "高準確度"],
  ["Custom", "自訂"],
  ["Epochs", "訓練輪數"],
  ["Batch Size", "批次大小"],
  ["Image Size", "影像尺寸"],
  ["Hardware Device", "硬體裝置"],
  ["Auto recommendation", "自動建議"],
  ["Auto Recommend Settings", "產生建議設定"],
  ["Learning Rate", "學習率"],
  ["Optimizer", "優化器"],
  ["Patience", "耐心值"],
  ["Workers", "工作程序"],
  ["Seed", "隨機種子"],
  ["Save Period", "儲存週期"],
  ["Close Mosaic Epochs", "關閉 Mosaic 的輪數"],
  ["Start Training", "開始訓練"],
  ["Stop Training", "停止訓練"],
  ["Start Training is disabled.", "開始訓練已停用。"],
  ["Live Training Monitor", "即時訓練監控"],
  ["No active training run.", "目前沒有進行中的訓練。"],
  ["Start training after readiness checks pass.", "就緒檢查通過後即可開始訓練。"],
  ["Progress", "進度"],
  ["Loss", "損失"],
  ["Metrics Dashboard", "訓練指標"],
  ["No training metrics yet.", "尚無訓練指標。"],
  ["Complete a training run to view charts, artifacts, and trend diagnostics.", "完成一次訓練後可查看圖表、產物與趨勢診斷。"],
  ["Primary Metrics", "主要指標"],
  ["Loss Breakdown", "Loss 分解"],
  ["Mask Metrics", "Mask 指標"],
  ["Box Metrics", "Box 指標"],
  ["Report View", "報告檢視"],
  ["Show Raw Curve", "顯示原始曲線"],
  ["Show EMA Smooth", "顯示 EMA 平滑"],
  ["Smooth Factor", "平滑係數"],
  ["Convergence Diagnostic", "收斂診斷"],
  ["Best Epoch:", "最佳 Epoch："],
  ["Platform Score:", "平台分數："],
  ["History & Event Logs", "歷史與事件紀錄"],
  ["Epoch History", "Epoch 歷史"],
  ["Event Log", "事件紀錄"],
  ["No epoch history yet.", "尚無 epoch 歷史。"],
  ["No training events yet.", "尚無訓練事件。"],
  ["Model Artifacts", "模型產物"],
  ["No artifacts yet. Complete a training run to see best.pt, last.pt, metrics, and reports.", "尚無產物。完成一次訓練後可查看 best.pt、last.pt、metrics 與報告。"],
  ["Run History", "Run 歷史"],
  ["No training runs yet.", "尚無訓練 run。"],
  ["Training Readiness: Blocked", "訓練就緒：已阻擋"],
  ["Training Readiness: Ready", "訓練就緒：可訓練"],
  ["Fix these items before editing training settings or starting a run.", "請先修正以下項目，再編輯訓練設定或啟動訓練。"],
  ["Readiness: pass", "就緒：通過"],
  ["Ready", "已就緒"],
  ["Blocked", "已阻擋"],
  ["Missing", "缺少"],
  ["Not ready", "尚未就緒"],
  ["Not Ready", "尚未就緒"],
  ["Not started", "尚未開始"],
  ["Available", "可用"],
  ["Unavailable", "不可用"],
  ["Exists", "存在"],
  ["Complete", "完成"],
  ["Completed", "已完成"],
  ["Failed", "失敗"],
  ["Stopped", "已停止"],
  ["Running", "執行中"],
  ["Training complete", "訓練完成"],
  ["Training failed", "訓練失敗"],
  ["Stopping training", "正在停止訓練"],
  ["Training in progress", "訓練進行中"],
  ["Loading run", "載入 run"],
  ["Failed to load run history.", "載入 run 歷史失敗。"],
  ["Export ONNX", "匯出 ONNX"],
  ["Exporting best.pt to ONNX...", "正在將 best.pt 匯出為 ONNX..."],

  ["RNN Training", "RNN 訓練"],
  ["Start RNN", "開始 RNN"],
  ["Start RNN Disabled", "RNN 開始訓練已停用"],
  ["Start RNN Training", "開始 RNN 訓練"],
  ["New RNN Project", "新增 RNN 專案"],
  ["Feature columns", "特徵欄位"],
  ["Target column", "目標欄位"],
  ["Feature dim", "特徵維度"],
  ["Sequence length", "序列長度"],
  ["Stride", "步長"],
  ["Horizon", "預測步長"],
  ["Readiness", "就緒狀態"],
  ["Not Ready / Preview", "尚未就緒 / 預覽"],
  ["Training enabled", "可啟動訓練"],
  ["Readiness required", "需要通過就緒檢查"],
  ["Backend planned", "後端規劃中"],
  ["CSV required", "需要 CSV"],
  ["Needs CSV", "需要 CSV"],
  ["Manifest only", "僅 manifest"],
  ["Ready / CSV training enabled", "已就緒 / CSV 訓練可用"],
  ["Ready but CSV required for training", "已就緒，但訓練需要 CSV"],
  ["Checking...", "檢查中..."],
  ["Importing", "匯入中"],
  ["Sequence count", "序列數"],
  ["Window config", "切片設定"],
  ["Feature config mismatch", "特徵設定不一致"],
  ["previous RNN run(s) use different feature config. Existing runs are kept, but direct comparison may be inconsistent.", "個既有 RNN run 使用不同特徵設定。歷史 run 會保留，但直接比較可能不一致。"],
  ["RNN / XGBoost Evaluation", "RNN / XGBoost 評估"],
  ["Refresh Evaluation", "重新整理評估"],
  ["No RNN or XGBoost run has been loaded yet.", "尚未載入 RNN 或 XGBoost run。"],
  ["No RNN or XGBoost training run found for this project.", "此專案尚未找到 RNN 或 XGBoost 訓練 run。"],
  ["Loading sequence training metrics, artifacts, and run history...", "正在載入序列訓練指標、產物與 run 歷史..."],
  ["No artifacts.", "沒有產物。"],
  ["Artifacts", "產物"],
  ["Refresh Models", "重新整理模型"],
  ["Loading RNN models...", "正在載入 RNN 模型..."],
  ["Ready to run CSV sequence inference.", "已可執行 CSV 序列推論。"],
  ["Open a project before sequence inference.", "請先開啟專案再執行序列推論。"],
  ["Loading RNN models.", "正在載入 RNN 模型。"],
  ["Sequence inference is running.", "序列推論執行中。"],
  ["Sequences", "序列"],
  ["Predictions", "預測"],
  ["Run", "Run"],
  ["Created", "建立時間"],
  ["Sequence / Class", "序列 / 類別"],
  ["Prediction", "預測"],
  ["Confidence", "信心分數"],
  ["Model Guide", "模型說明"],
  ["LSTM Classification", "LSTM 分類"],
  ["LSTM Regression", "LSTM 回歸"],
  ["GRU Classification", "GRU 分類"],
  ["GRU Regression", "GRU 回歸"],
  ["BiLSTM Classification", "BiLSTM 分類"],
  ["BiLSTM Regression", "BiLSTM 回歸"],
  ["XGBoost Classification", "XGBoost 分類"],
  ["XGBoost Regression", "XGBoost 回歸"],
  ["LSTM Classifier", "LSTM 分類器"],
  ["LSTM Regressor", "LSTM 回歸器"],
  ["GRU Classifier", "GRU 分類器"],
  ["GRU Regressor", "GRU 回歸器"],
  ["BiLSTM Classifier", "BiLSTM 分類器"],
  ["BiLSTM Regressor", "BiLSTM 回歸器"],
  ["XGBoost Classifier", "XGBoost 分類器"],
  ["XGBoost Regressor", "XGBoost 回歸器"],
  ["Loading model guide...", "正在載入模型說明..."],
  ["No guide found for this model/task combination.", "找不到此模型 / 任務組合的說明。"],
  ["Missing", "缺少"],
  ["Loading", "載入中"],

  ["Evaluation Status", "評估狀態"],
  ["Run Evaluation", "執行評估"],
  ["Inference Status", "推論狀態"],
  ["Inference Lab", "推論測試"],
  ["Open Inference Lab", "開啟推論測試"],
  ["Run Inference", "執行推論"],
  ["Running", "執行中"],
  ["Task mismatch", "任務不相符"],
  ["Inference completed", "推論完成"],
  ["Loading inference jobs...", "正在載入推論紀錄..."],
  ["Loading inference result...", "正在載入推論結果..."],
  ["Failed to load inference result:", "載入推論結果失敗："],
  ["Failed to load inference history:", "載入推論歷史失敗："],

  ["Auto-Labeling Status", "自動標註狀態"],
  ["Start Auto-Labeling", "開始自動標註"],
  ["Available models", "可用模型"],
  ["Draft Preview / Review", "草稿預覽 / 審查"],
  ["Hard Case", "困難案例"],
  ["Checkpoint", "檢查點"],

  ["Export Status", "匯出狀態"],
  ["Export Model", "匯出模型"],
  ["Last export", "最後匯出"],
  ["Report", "報告"],
  ["Refresh Runs", "重新整理 Run"],
  ["Available Runs", "可用 Run"],
  ["Preview / Result", "預覽 / 結果"],

  ["Source", "來源"],
  ["Target", "目標"],
  ["Target exists", "目標已存在"],
  ["Copy Selected Projects", "複製選取專案"],
  ["Source and target are already the same project root.", "來源與目標已經是相同專案根目錄。"],
  ["Error", "錯誤"],

  ["Open Projects or Browse History to choose a project.", "請前往專案或瀏覽歷史選擇專案。"],
  ["No project is open for this page.", "此頁目前尚未開啟專案。"],
  ["No active project. Most workflow actions are waiting for a project.", "尚未開啟專案，大多數流程操作都會暫停。"],
  ["Create a new project or open one from Browse History.", "請建立新專案，或從瀏覽歷史開啟既有專案。"],
  ["Use New Project to create a project.", "使用新增專案建立專案。"],
  ["Use Browse History to open an existing project.", "使用瀏覽歷史開啟既有專案。"],
  ["No projects are available yet.", "目前尚無專案。"],
  ["Create or open a project to see dashboard readiness.", "建立或開啟專案後即可查看總覽就緒狀態。"],
  ["Create or open a project first.", "請先建立或開啟專案。"],
  ["Open Training and start a configured run.", "開啟模型訓練並啟動已設定的 run。"],
  ["Review settings, then start training.", "確認設定後開始訓練。"],
  ["Go to Dataset and import images.", "前往資料集匯入圖片。"],
  ["Create Train / Val / Test split.", "建立 Train / Val / Test 分散。"],
  ["Available models do not match the project task type.", "可用模型與目前專案任務類型不相符。"],
  ["Dataset is missing. Import images before training.", "資料集缺少內容，請先匯入圖片再訓練。"],
  ["GPU is unavailable or backend health is missing; training may be slow.", "GPU 不可用或後端健康狀態缺失，訓練可能較慢。"],
  ["Open Browse History for project file details.", "開啟瀏覽歷史查看專案檔案細節。"],
  ["Review recent imports, runs, and exports.", "檢查最近的匯入、run 與匯出。"],
]);

const STATIC_REPLACEMENTS = Array.from(ZH_TEXT.entries()).sort((a, b) => b[0].length - a[0].length);
const I18N_REPLACEMENT_KEYS = Array.from(I18N_TEXT_KEYS.entries()).sort((a, b) => b[0].length - a[0].length);
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "CODE", "PRE", "TEXTAREA"]);
let translating = false;
let translateI18nKey = null;
const originalTextNodes = new WeakMap();
const originalAttributes = new WeakMap();

export function configureI18nFallback(translator) {
  translateI18nKey = typeof translator === "function" ? translator : null;
}

function translateByKey(key) {
  if (!translateI18nKey) return "";
  const value = translateI18nKey(key);
  if (value == null || value === key) return "";
  return String(value);
}

function translateFallbackToken(token) {
  const key = I18N_TEXT_KEYS.get(token);
  if (key) {
    const translated = translateByKey(key);
    if (translated) return translated;
  }
  return ZH_TEXT.get(token) || "";
}

export function localizeUiText(value) {
  if (value == null) return value;
  const source = String(value);
  const trimmed = source.trim();
  if (!trimmed || !/[A-Za-z]/.test(trimmed)) return source;
  const exact = translateFallbackToken(trimmed);
  if (exact) return source.replace(trimmed, exact);

  let translated = source;
  for (const [from, key] of I18N_REPLACEMENT_KEYS) {
    const to = translateByKey(key);
    if (to && translated.includes(from)) translated = translated.split(from).join(to);
  }
  for (const [from, to] of STATIC_REPLACEMENTS) {
    if (translated.includes(from)) translated = translated.split(from).join(to);
  }
  return translated;
}

function shouldSkipNode(node) {
  const parent = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
  if (!parent) return true;
  if (SKIP_TAGS.has(parent.tagName)) return true;
  if (parent.closest?.("[data-i18n-skip], .no-i18n")) return true;
  return false;
}

function localizeTextNode(node) {
  if (shouldSkipNode(node)) return;
  const next = localizeUiText(node.nodeValue);
  if (next !== node.nodeValue) {
    if (!originalTextNodes.has(node)) originalTextNodes.set(node, node.nodeValue);
    node.nodeValue = next;
  }
}

function localizeElementAttributes(el) {
  if (!el || shouldSkipNode(el)) return;
  for (const attr of ["placeholder", "title", "aria-label", "data-tooltip", "alt"]) {
    if (!el.hasAttribute?.(attr)) continue;
    const current = el.getAttribute(attr);
    const next = localizeUiText(current);
    if (next !== current) {
      if (!originalAttributes.has(el)) originalAttributes.set(el, new Map());
      const attrMap = originalAttributes.get(el);
      if (!attrMap.has(attr)) attrMap.set(attr, current);
      el.setAttribute(attr, next);
    }
  }
}

export function applyZhFallbackTranslations(root = document.body) {
  if (!root || translating) return;
  translating = true;
  try {
    if (root.nodeType === Node.TEXT_NODE) {
      localizeTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;

    if (root.nodeType === Node.ELEMENT_NODE) localizeElementAttributes(root);
    const elements = root.querySelectorAll?.("[placeholder], [title], [aria-label], [data-tooltip], [alt]") || [];
    elements.forEach(localizeElementAttributes);

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(localizeTextNode);
  } finally {
    translating = false;
  }
}

function restoreTextNode(node) {
  if (!originalTextNodes.has(node)) return;
  node.nodeValue = originalTextNodes.get(node);
  originalTextNodes.delete(node);
}

function restoreElementAttributes(el) {
  const attrMap = originalAttributes.get(el);
  if (!attrMap) return;
  for (const [attr, value] of attrMap.entries()) {
    el.setAttribute(attr, value);
  }
  originalAttributes.delete(el);
}

export function restoreFallbackTranslations(root = document.body) {
  if (!root || translating) return;
  translating = true;
  try {
    if (root.nodeType === Node.TEXT_NODE) {
      restoreTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;

    if (root.nodeType === Node.ELEMENT_NODE) restoreElementAttributes(root);
    const elements = root.querySelectorAll?.("[placeholder], [title], [aria-label], [data-tooltip], [alt]") || [];
    elements.forEach(restoreElementAttributes);

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(restoreTextNode);
  } finally {
    translating = false;
  }
}
