import { scaleRgba } from './utils.js';

const charts = [];
const chartAnimationDuration = 100;  // ms
let commandColors, commandLabels;

export const createCharts = (thres, _commandColors, _commandLabels) => {
    if (charts.length > 0) removeCharts(); // remove existing charts

    commandColors = _commandColors;
    commandLabels = _commandLabels;

    [...document.getElementsByClassName('likelihood-chart')].forEach((canvas) => {
        // create a config for each chart so that they don't share the same data
        const config = {
            type: 'bar',
            data: {
                labels: Array(commandLabels.length).fill(''),  // neccesary
                datasets: [{
                    data: Array(commandLabels.length).fill(0.4),
                    backgroundColor: commandColors,
                    borderColor: commandColors.map(rgba => scaleRgba(rgba, 0.7, 1)),
                    borderWidth: 1,
                }]
            },
            options: {
                plugins: {
                    legend: {
                        display: false,
                    },
                    annotation: {
                        annotations: {
                            lineThres: {
                                type: 'line',
                                yMin: thres,
                                yMax: thres,
                                borderColor: 'black',
                                borderWidth: 1,
                                borderDash: [4, 4], // dashed line style
                            }
                        }
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            display: false,
                        },
                        grid: {
                            display: false,
                        }
                    },
                    y: {
                        beginAtZero: true,
                        max: thres / 0.7,
                        ticks: {
                            display: false,
                            // display: true,
                            // stepSize: 0.1,
                            // callback: (value) => [0, 0.3, 1].includes(value) ? value : '',
                        },
                        grid: {
                            display: false,
                        }
                    },
                },
                animation: {
                    duration: chartAnimationDuration,
                },
                maintainAspectRatio: false,
                backgroundColor: 'white',
            },
        };
        const chart = new Chart(canvas.getContext('2d'), config);
        chart.update();
        charts.push(chart);
        canvas.parentElement.style.display = 'block';  // show the parent container
    });
}

export const removeCharts = () => {
    while (charts.length > 0) {
        const chart = charts.pop();
        chart.canvas.parentElement.style.display = 'none';
        chart.destroy();
    }
};

export const updateChartData = (agentId, likelihoods, nextAcceptableCommands) => {
    const chart = charts[agentId];
    if (chart === undefined) {
        console.error('Chart not initialized.');
        return;
    }
    // update only the likelihood of acceptable commands
    chart.data.datasets[0].data = likelihoods.map((likelihood, i) =>
        nextAcceptableCommands.includes(commandLabels[i]) ? likelihood : chart.data.datasets[0].data[i]
    );
    chart.update();
}

export const updateChartColor = (agentId, currentCommand, nextAcceptableCommands) => {
    const chart = charts[agentId];
    if (chart === undefined) {
        console.error('Chart not initialized.');
        return;
    }
    chart.data.datasets[0].backgroundColor = [...Array(commandLabels.length).keys()].map(barId => getBarColor(barId, currentCommand));
    chart.data.datasets[0].borderColor = [...Array(commandLabels.length).keys()].map(barId => getBorderColor(barId, currentCommand, nextAcceptableCommands));
    chart.update();
}

const getBarColor = (barId, currentCommand) => {
    // highlight the current command bar
    if (commandLabels[barId] === currentCommand) return scaleRgba(commandColors[barId], 1, 1);
    // nothing for border color
    return commandColors[barId];
}

const getBorderColor = (barId, currentCommand, nextAcceptableCommands) => {
    // add black border to the current command bar
    if (commandLabels[barId] === currentCommand) return 'rgba(0, 0, 0, 1)';
    // remove border from the unacceptable command bars
    if (nextAcceptableCommands.includes(commandLabels[barId])) return scaleRgba(commandColors[barId], 0.7, 1);
    return 'rgba(255, 255, 255, 1)';
}