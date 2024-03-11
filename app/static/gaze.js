let surfaceOrigin, surfaceSize;

export const showAprilTags = () => {
    [...document.getElementsByClassName('apriltag')].forEach((tag) => {
        tag.style.display = 'block';
    });

    // get surface coordinates
    const topLeftTag = document.querySelector('.apriltag.top-left');
    const bottomRightTag = document.querySelector('.apriltag.bottom-right');
    const { top, left } = topLeftTag.getBoundingClientRect();
    const { bottom, right } = bottomRightTag.getBoundingClientRect();
    const margin = topLeftTag.width / 10;  // width of white area around the tag
    const [left_, top_] = [left + margin, top + margin];
    const [right_, bottom_] = [right - margin, bottom - margin];
    surfaceOrigin = [left_, top_];
    surfaceSize = [right_ - left_, bottom_ - top_];
}

export const hideAprilTags = () => {
    [...document.getElementsByClassName('apriltag')].forEach((tag) => {
        tag.style.display = 'none';
    });
}

export const mapGazeToSurface = (x, y) => {
    // [x, y] in the range of [0, 1]^2
    const gaze = [
        surfaceOrigin[0] + surfaceSize[0] * x,
        surfaceOrigin[1] + surfaceSize[1] * y,
    ];
    return gaze;
}
