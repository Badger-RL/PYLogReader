from enum import Enum, auto


class MessageID(Enum):
    undefined = 0
    idNumOfDataMessageIDs = undefined
    idFrameBegin = auto()
    idFrameFinished = auto()
    idActivationGraph = auto()
    idAnnotation = auto()
    idCameraImage = auto()
    idInertialSensorData = auto()
    idJointCalibration = auto()
    idJointRequest = auto()
    idJointSensorData = auto()
    idJPEGImage = auto()
    idMotionRequest = auto()
    idStopwatch = auto()
    idAlternativeRobotPoseHypothesis = auto()
    idArmMotionRequest = auto()
    idAudioData = auto()
    idBallModel = auto()
    idBallPercept = auto()
    idBallSpots = auto()
    idBehaviorStatus = auto()
    idBodyContour = auto()
    idCameraCalibration = auto()
    idCameraInfo = auto()
    idCameraMatrix = auto()
    idCirclePercept = auto()
    idFallDownState = auto()
    idFieldBoundary = auto()
    idFieldFeatureOverview = auto()
    idFootOffset = auto()
    idFootSupport = auto()
    idFrameInfo = auto()
    idFsrData = auto()
    idFsrSensorData = auto()
    idGameControllerData = auto()
    idGameState = auto()
    idGyroOffset = auto()
    idGyroState = auto()
    idGroundContactState = auto()
    idGroundTruthOdometryData = auto()
    idGroundTruthWorldState = auto()
    idHeadMotionRequest = auto()
    idIMUCalibration = auto()
    idImageCoordinateSystem = auto()
    idInertialData = auto()
    idJointAnglePred = auto()
    idJointAngles = auto()
    idJointLimits = auto()
    idJointPlay = auto()
    idKeypoints = auto()
    idKeyStates = auto()
    idLinesPercept = auto()
    idMotionInfo = auto()
    idObstacleModel = auto()
    idObstaclesFieldPercept = auto()
    idObstaclesImagePercept = auto()
    idOdometer = auto()
    idOdometryData = auto()
    idOdometryDataPreview = auto()
    idOdometryTranslationRequest = auto()
    idPenaltyMarkPercept = auto()
    idReceivedTeamMessages = auto()
    idRefereePercept = auto()
    idRobotDimensions = auto()
    idRobotHealth = auto()
    idRobotPose = auto()
    idRobotStableState = auto()
    idSelfLocalizationHypotheses = auto()
    idSideInformation = auto()
    idSkillRequest = auto()
    idStaticJointPoses = auto()
    idStrategyStatus = auto()
    idSystemSensorData = auto()
    idTeammatesBallModel = auto()
    idTeamData = auto()
    idWalkGenerator = auto()
    idWalkStepData = auto()
    idWalkingEngineOutput = auto()
    idWalkLearner = auto()
    idWhistle = auto()
    idConsole = auto()
    numOfDataMessageIDs = idConsole
    idDebugDataChangeRequest = auto()
    idDebugDataResponse = auto()
    idDebugDrawing = auto()
    idDebugDrawing3D = auto()
    idDebugImage = auto()
    idDebugRequest = auto()
    idDebugResponse = auto()
    idDrawingManager = auto()
    idDrawingManager3D = auto()
    idLogResponse = auto()
    idModuleRequest = auto()
    idModuleTable = auto()
    idPlot = auto()
    idRobotName = auto()
    idText = auto()
    idThread = auto()
    idTypeInfo = auto()
    idTypeInfoRequest = auto()