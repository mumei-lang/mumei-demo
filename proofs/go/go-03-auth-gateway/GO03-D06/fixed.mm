struct Rotation {
    epoch: i64,
    sessions: i64,
}

atom rotateHandler(epoch: i64, sessions: i64) -> Rotation
    requires: epoch >= 0 && sessions >= 0;
    ensures: result.sessions == 0 && result.epoch == epoch + 1;
    body: {
        Rotation { epoch: epoch + 1, sessions: 0 }
    }
